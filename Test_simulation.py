import salabim as sim
import random

sim.yieldless(False)

# === SIMULATION ENVIRONMENT ===
env = sim.Environment(trace=False)

# === CONFIGURATION FLAGS ===
USE_SWAPPING = True         # Set False to use direct charging
USE_SOC_WINDOW = True       # True = charge to 80%, else full charge
TEST_MODE = True            # Shorter sim duration for dev/testing

# === PARAMETERS ===
CHARGING_RATE = 300  # kW
BATTERY_CAPACITY = 191  # kWh
AGV_SPEED = 25 * 1000 / 3600  # m/s (25 km/h)
SWAPPING_TIME = 180  # 3 minutes
LOADING_TIME = 18  # seconds
UNLOADING_TIME = 18  # seconds
SIM_TIME = 2 * 60 * 60 if TEST_MODE else 24 * 60 * 60
SOC_MIN = 20
SOC_MAX = 80 if USE_SOC_WINDOW else 100

# === MONITORS ===
battery_soc_monitor = sim.Monitor("Battery SOC")
battery_queue_monitor = sim.Monitor("Battery Queue Length")
delivery_time_monitor = sim.Monitor("Container Delivery Time")
battery_deg_monitor = sim.Monitor("Battery Degradation")

# === QUEUES ===
BatteryQueue = sim.Queue("AvailableBatteries")
ContainerQueue = sim.Queue("ContainerQueue")
AGVQueue = sim.Queue("IdleAGVs")

# === COMPONENT CLASSES ===

class Battery(sim.Component):
    def setup(self, soc=100):
        self.soc = soc
        self.degradation = 0

    def charge_to_target(self, target_soc=SOC_MAX):
        charge_needed = max(0, target_soc - self.soc)
        return (charge_needed / 100) * BATTERY_CAPACITY / CHARGING_RATE * 3600

    def update_degradation(self):
        if self.soc < 20 or self.soc > 80:
            self.degradation += 0.02
        else:
            self.degradation += 0.01

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
                old_battery = agv.battery
                ChargerBattery.queue.append(old_battery)
                if ChargerBattery.ispassive():
                    ChargerBattery.activate()
                yield self.hold(SWAPPING_TIME)
                new_battery = BatteryQueue.pop()
                agv.battery = new_battery
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
                charge_time = battery.charge_to_target()
                battery.update_degradation()
                battery_deg_monitor.tally(battery.degradation)
                yield self.hold(charge_time)
                battery.soc = SOC_MAX
                BatteryQueue.append(battery)
            else:
                yield self.passivate()

class AGV(sim.Component):
    def setup(self):
        self.battery = Battery(soc=100)
        self.selected_for_charging = False

    def process(self):
        while True:
            AGVQueue.append(self)
            self.passivate()

            if ContainerQueue:
                container = ContainerQueue.pop()
            else:
                continue
            start_time = env.now()

            yield self.hold(LOADING_TIME)
            yield self.hold(self.route_time())
            yield self.hold(UNLOADING_TIME)

            delivery_time_monitor.tally(env.now() - container.arrival_time)
            self.battery.soc -= random.uniform(5, 15)
            battery_soc_monitor.tally(self.battery.soc)

            if self.battery.soc < SOC_MIN:
                self.selected_for_charging = True

            if self.selected_for_charging:
                if USE_SWAPPING:
                    Swapper.queue.append(self)
                    if Swapper.ispassive():
                        Swapper.activate()
                    self.passivate()
                else:
                    Charger.queue.append(self)
                    if Charger.ispassive():
                        Charger.activate()
                    self.passivate()

    def route_time(self):
        distance = 700  # meters
        return distance / AGV_SPEED

class ContainerGenerator(sim.Component):
    def process(self):
        while True:
            # Gamma-distributed time between container batch arrivals (simulate vessel arrival)
            yield self.hold(random.gammavariate(2, 3600))  # e.g., 2-hour average between ships

            # === Batch size based on Gamma(shape=8, scale=883.125), capped at 24000 ===
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

for _ in range(20):
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
print(f"Final Avg Delivery Time: {delivery_time_monitor.mean():.2f}s")
print(f"Final Avg Battery Degradation: {battery_deg_monitor.mean():.4f}")
