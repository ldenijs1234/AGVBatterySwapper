import salabim as sim
import random

sim.yieldless(False)

# === SIMULATION ENVIRONMENT ===
env = sim.Environment(trace=False)

# === CONFIGURATION FLAGS ===
USE_SWAPPING = True
USE_SOC_WINDOW = True
TEST_MODE = True

# === PARAMETERS ===
CHARGING_RATE = 300  # kW
BATTERY_CAPACITY = 191  # kWh
AGV_SPEED = 25 * 1000 / 3600  # m/s
SWAPPING_TIME = 180
LOADING_TIME = 18
UNLOADING_TIME = 18
SIM_TIME = 2 * 60 if TEST_MODE else 24 * 60 * 60
SOC_MIN = 20
SOC_MAX = 80 if USE_SOC_WINDOW else 100

# === MONITORS ===
battery_soc_monitor = sim.Monitor("Battery SOC")
battery_queue_monitor = sim.Monitor("Battery Queue Length")
delivery_time_monitor = sim.Monitor("Container Delivery Time")
battery_deg_monitor = sim.Monitor("Battery Degradation")
soh_monitor = sim.Monitor("Battery SOH")

# === QUEUES ===
BatteryQueue = sim.Queue("AvailableBatteries")
ContainerQueue = sim.Queue("ContainerQueue")
AGVQueue = sim.Queue("IdleAGVs")

# === COMPONENT CLASSES ===

class Battery(sim.Component):
    def setup(self, soc=100, soh=100):
        self.soc = soc
        self.soh = soh

    def charge_to_target(self, target_soc=SOC_MAX):
        charge_needed = max(0, target_soc - self.soc)
        return (charge_needed / 100) * BATTERY_CAPACITY / CHARGING_RATE * 3600

    def update_degradation(self):
        if self.soc < 20 or self.soc > 80:
            self.soh -= 0.02
        else:
            self.soh -= 0.01
        soh_monitor.tally(self.soh)


class Container(sim.Component):
    def setup(self):
        self.arrival_time = env.now()


class ChargingStation(sim.Component):
    def setup(self):
        self.queue = sim.Queue("ChargingStationQueue")

    def process(self):
        while True:
            if self.queue:
                agv = self.queue.pop()
                charge_time = agv.battery.charge_to_target()
                yield self.hold(charge_time)
                agv.battery.soc = SOC_MAX
                agv.selected_for_charging = False
                agv.activate()
            else:
                yield self.passivate()


class SwappingStation(sim.Component):
    def setup(self):
        self.queue = sim.Queue("SwappingStationQueue")

    def process(self):
        while True:
            if self.queue:
                agv = self.queue.pop()

                # If the AGV has an old battery, send it for charging
                if agv.battery:
                    ChargerBattery.queue.append(agv.battery)
                    if ChargerBattery.ispassive():
                        ChargerBattery.activate()
                    yield self.hold(SWAPPING_TIME)

                # Assign new battery
                new_battery = BatteryQueue.pop()
                agv.battery = new_battery

                yield self.hold(SWAPPING_TIME)
                agv.selected_for_charging = False
                agv.activate()
            else:
                yield self.passivate()


class ChargerBatteryComponent(sim.Component):
    def setup(self):
        self.queue = sim.Queue("BatteryChargingQueue")

    def process(self):
        while True:
            if self.queue:
                battery = self.queue.pop()
                battery.update_degradation()
                battery_deg_monitor.tally(100 - battery.soh)
                charge_time = battery.charge_to_target()
                yield self.hold(charge_time)
                battery.soc = SOC_MAX
                BatteryQueue.append(battery)
            else:
                yield self.passivate()


class AGV(sim.Component):
    def setup(self):
        self.battery = None
        self.selected_for_charging = False

    def process(self):
        while True:
            if not self.battery:
                self.passivate()

            if ContainerQueue:
                container = ContainerQueue.pop()
                yield self.hold(LOADING_TIME)
                yield self.hold(self.route_time())
                yield self.hold(UNLOADING_TIME)
                delivery_time_monitor.tally(env.now() - container.arrival_time)

                self.battery.soc -= random.uniform(5, 15)
                battery_soc_monitor.tally(self.battery.soc)

                if self.battery.soc < SOC_MIN:
                    self.selected_for_charging = True

                if self.selected_for_charging:
                    Swapper.queue.append(self)
                    if Swapper.ispassive():
                        Swapper.activate()
                    self.passivate()

            else:
                AGVQueue.append(self)
                self.passivate()

    def route_time(self):
        distance = 700  # meters
        return distance / AGV_SPEED


class ContainerGenerator(sim.Component):
    def process(self):
        while True:
            wait_time = 1 if TEST_MODE else random.gammavariate(2, 3600)
            yield self.hold(wait_time)

            mean = 7065
            shape = 8
            scale = mean / shape
            max_val = 24000
            batch_size = min(int(random.gammavariate(shape, scale)), max_val)

            print(f"\n--- New batch of {batch_size} containers at {env.now():.0f}s ---")

            for _ in range(batch_size):
                container = Container()
                ContainerQueue.append(container)

                # Wake up an AGV if any are idle
                if AGVQueue:
                    agv = AGVQueue.pop()
                    agv.activate()

class MonitorReporter(sim.Component):
    def process(self):
        while True:
            yield self.hold(300)
            battery_queue_monitor.tally(len(BatteryQueue))
            print(f"Time: {env.now():.0f}s")
            print(f"BatteryQueue Length: {len(BatteryQueue)}")
            print(f"Charging Queue: {len(Charger.queue)}")
            print(f"Swapping Queue: {len(Swapper.queue)}")
            print(f"Avg SOC: {battery_soc_monitor.mean():.2f}%")
            print(f"Avg Delivery Time: {delivery_time_monitor.mean():.2f}s")
            print(f"Avg Battery Degradation: {battery_deg_monitor.mean():.4f}")
            print("-" * 40)

# === SYSTEM INITIALIZATION ===

Charger = ChargingStation()
Swapper = SwappingStation()
ChargerBattery = ChargerBatteryComponent()

for _ in range(154):
    BatteryQueue.append(Battery(soc=SOC_MAX))

for _ in range(84):  # Fixed AGV pool
    AGV()

ContainerGenerator()
MonitorReporter()

# === RUN SIMULATION ===
env.run(till=SIM_TIME)

# === FINAL OUTPUT ===
print("Simulation complete.")
print(f"Final Battery Queue Length: {len(BatteryQueue)}")
print(f"Final Avg SOC: {battery_soc_monitor.mean():.2f}%")
print(f"Final Avg Battery SOH: {battery_soh_monitor.mean():.2f}%")
print(f"Final Avg Delivery Time: {delivery_time_monitor.mean():.2f}s")
print(f"Final Avg Battery Degradation: {battery_deg_monitor.mean():.4f}")
