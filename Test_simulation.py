import salabim as sim
import random

sim.yieldless(False)


# === INITIALIZATION ===
env = sim.Environment(trace=False)

# === CONFIGURATION ===
USE_SWAPPING = True  # Toggle between swapping and charging

# === PARAMETERS ===
CHARGING_RATE = 300  # kW
BATTERY_CAPACITY = 191  # kWh
AGV_SPEED_KMPH = 25
AGV_SPEED = AGV_SPEED_KMPH * 1000 / 3600  # m/s
SWAPPING_TIME = sim.Uniform(240, 300)
LOADING_TIME = sim.Uniform(15, 30)
UNLOADING_TIME = sim.Uniform(15, 30)
SIM_TIME = 24 * 60 * 60  # seconds in 1 day

# === MONITORS ===
battery_soc_monitor = sim.Monitor("Battery SOC")
battery_queue_monitor = sim.Monitor("Battery Queue Length")

# === BATTERY COMPONENT ===
class Battery(sim.Component):
    def setup(self, soc=100):
        self.soc = soc

    def charge_to_target(self, target_soc=80):
        charge_needed = max(0, target_soc - self.soc)
        return (charge_needed / 100) * BATTERY_CAPACITY / CHARGING_RATE * 3600  # seconds

# === SIMULATION COMPONENTS ===
class ChargingStation(sim.Component):
    def setup(self):
        self.queue = sim.Queue("ChargingStationQueue")

    def process(self):
        while True:
            if self.queue:
                agv = self.queue.pop()
                charge_time = agv.battery.charge_to_target()
                yield self.hold(charge_time)
                agv.battery.soc = 80
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
                yield self.hold(SWAPPING_TIME.sample())
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
                yield self.hold(charge_time)
                battery.soc = 80
                BatteryQueue.append(battery)
            else:
                yield self.passivate()

class AGV(sim.Component):
    def setup(self):
        self.battery = Battery(soc=100)
        self.selected_for_charging = False

    def process(self):
        while True:
            yield self.hold(random.uniform(60, 120))  # travel to pickup
            yield self.hold(LOADING_TIME.sample())
            yield self.hold(random.uniform(60, 120))  # travel to drop-off
            yield self.hold(UNLOADING_TIME.sample())

            self.battery.soc -= random.uniform(5, 15)
            battery_soc_monitor.tally(self.battery.soc)

            if self.battery.soc < 20:
                self.selected_for_charging = True

            if self.selected_for_charging:
                if USE_SWAPPING:
                    if self not in Swapper.queue:
                        Swapper.queue.append(self)
                        if Swapper.ispassive():
                            Swapper.activate()
                        self.passivate()
                else:
                    if self not in Charger.queue:
                        Charger.queue.append(self)
                        if Charger.ispassive():
                            Charger.activate()
                        self.passivate()

class ContainerGenerator(sim.Component):
    def process(self):
        while True:
            yield self.hold(sim.Exponential(30).sample())
            agv = AGV()
            agv.activate()

# === PARAMETRIC REPORTING COMPONENT ===
class MonitorReporter(sim.Component):
    def process(self):
        while True:
            yield self.hold(300)  # every 5 minutes
            battery_queue_monitor.tally(len(BatteryQueue))
            print(f"Time: {env.now():.0f}s")
            print(f"BatteryQueue Length: {len(BatteryQueue)}")
            print(f"Charging Queue Length: {len(Charger.queue)}")
            print(f"Swapping Queue Length: {len(Swapper.queue)}")
            print(f"Average Battery SOC: {battery_soc_monitor.mean():.2f}%")
            print("-" * 40)

# === INITIALIZATION ===
env = sim.Environment(trace=False)
BatteryQueue = sim.Queue("AvailableBatteries")

Charger = ChargingStation()
Swapper = SwappingStation()
ChargerBattery = ChargerBatteryComponent()

for _ in range(10):
    BatteryQueue.append(Battery(soc=80))

ContainerGenerator()
MonitorReporter()

# === RUN SIMULATION ===
env.run(till=SIM_TIME)

# === FINAL OUTPUT ===
print("Simulation complete.")
print(f"Final Battery Queue Length: {len(BatteryQueue)}")
print(f"Charging Queue (AGVs): {len(Charger.queue)}")
print(f"Swapping Queue (AGVs): {len(Swapper.queue)}")
print(f"Final Average SOC: {battery_soc_monitor.mean():.2f}%")