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
POWER_CONSUMPTION = 17 / 25  # kWh/km
IDLE_POWER_CONSUMPTION = 9  # kWh
SIM_TIME = 24 * 60 * 60 if TEST_MODE else 24 * 60 * 60
SOC_MIN = 20
SOC_MAX = 80 if USE_SOC_WINDOW else 100

# === MONITORS ===
battery_soc_monitor = sim.Monitor("Battery SOC")
battery_soh_monitor = sim.Monitor("Battery SOH")

battery_queue_monitor = sim.Monitor("Battery Queue Length")
container_queue_monitor = sim.Monitor("Container Queue Length")
charging_time_monitor = sim.Monitor("Battery Charging Time")
container_delivery_time_monitor = sim.Monitor("Container Delivery Time")
agv_idle_time_monitor = sim.Monitor("AGV Idle Time")

charge_monitor = sim.Monitor("AGV Charges")
container_monitor = sim.Monitor("Containers Delivered")


# === QUEUES ===
BatteryQueue = sim.Queue("AvailableBatteries")
ContainerQueue = sim.Queue("ContainerQueue")
SwappingQueue = sim.Queue("SwappingQueue")
ChargingQueue = sim.Queue("ChargingQueue")

AGVQueue = sim.Queue("IdleAGVs")

# === COMPONENT CLASSES ===
class Battery(sim.Component):
    def setup(self, soc=100):
        self.capacity = BATTERY_CAPACITY
        self.energy = soc / 100 * BATTERY_CAPACITY
        self.soh = 100

    def soc(self):
        return (self.energy / self.capacity) * 100
    
    def process(self):
        while True:
            # Wait to be activated by ChargingStation
            yield self.passivate()
            yield from self.charge()
            start = self.env.now()
            charge_time = max(0, (SOC_MAX - self.soc()) * BATTERY_CAPACITY / CHARGING_RATE * 3600)
            yield self.hold(charge_time)

            charging_time_monitor.tally(self.env.now() - start)
            self.energy = SOC_MAX  * BATTERY_CAPACITY  # restore energy to SOC_MAX
            battery_soc_monitor.tally(self.soc())

            BatteryQueue.add(self)  # Always re-enter queue after charging


    def charge(self):
        start = self.env.now()
        duration = max(0, (SOC_MAX - self.soc()) * BATTERY_CAPACITY / CHARGING_RATE * 3600)
        yield self.hold(duration)
        charging_time_monitor.tally(self.env.now() - start)
        self.energy = SOC_MAX * self.capacity
        battery_soc_monitor.tally(self.energy / self.capacity * 100)

        BatteryQueue.add(self)  # Always re-enter queue after charging


class AGV(sim.Component):
    def setup(self):
        self.battery = None
        self.distance_traveled = 0  # optional tracking
        self.charge_count = 0
        self.containers_handled = 0

    def process(self):
        while True:
            # Battery swap only if needed
            while self.battery is None:
                SwappingQueue.add(self)
                yield self.passivate()

                # Get a battery
                while len(BatteryQueue) == 0:
                    AGVQueue.add(self)
                    yield self.passivate()

                self.battery = BatteryQueue.pop()
                yield self.hold(SWAPPING_TIME)


            # Get a container
            if len(ContainerQueue) == 0:
                wait_start = self.env.now()

                AGVQueue.add(self)
                yield self.passivate()

                # On reactivation — calculate idle energy usage
                idle_duration = self.env.now() - wait_start
                idle_energy_used = IDLE_POWER_CONSUMPTION * (idle_duration / 3600) # in kWh 
                self.battery.energy -= idle_energy_used
                self.battery.energy = max(0, self.battery.energy)
                battery_soc_monitor.tally(self.battery.soc)

            # Proceed with container
            container = ContainerQueue.pop()
            pickup_time = self.env.now()
            yield self.hold(LOADING_TIME)

            # Drive
            travel_distance = random.uniform(30000, 1000000) # in meters 
            self.distance_traveled += travel_distance
            energy_used = POWER_CONSUMPTION / 1000 * travel_distance # kWh/m * m = kWh 
            self.battery.energy -= energy_used
            self.battery.energy = max(0, self.battery.energy)
            battery_soc_monitor.tally(self.battery.soc)

            yield self.hold(travel_distance / AGV_SPEED) # Hold time (s) based on speed 
            yield self.hold(UNLOADING_TIME)

            self.containers_handled += 1
            delivery_duration = self.env.now() - pickup_time
            container_delivery_time_monitor.tally(delivery_duration / 60) # Convert to minutes 

            # Battery check
            if self.battery.soc() < SOC_MIN:
                self.charge_count += 1
                ChargingQueue.add(self.battery)
                self.battery = None

            # Repeat
            continue

class Container(sim.Component):
    def setup(self):
        self.created_at = self.env.now()

class ContainerGenerator(sim.Component):
    def process(self):
        while True:
            ContainerQueue.add(Container())  # simple container stand-in
            container_queue_monitor.tally(len(ContainerQueue))
            yield self.hold(random.expovariate(1/60))  # 1 container per minute

class SwapperStation(sim.Component):
    def process(self):
        while True:
            if len(SwappingQueue) > 0:
                agv = SwappingQueue.pop()
                agv.activate()
            yield self.hold(1)


class ChargingStation(sim.Component):
    def process(self):
        while True:
            if len(ChargingQueue) > 0:
                battery = ChargingQueue.pop()
                battery.activate()

            yield self.hold(1)

class QueueLengthMonitor(sim.Component):
    def process(self):
        while True:
            battery_queue_monitor.tally(len(BatteryQueue))
            yield self.hold(60)  # record every 60 seconds


# === ENV SETUP ===
NUM_AGVS = 4
NUM_BATTERIES = 4

# Start all batteries fully charged
for _ in range(NUM_BATTERIES):
    BatteryQueue.add(Battery(soc=100))  # No .activate() needed

agvs = []

for _ in range(NUM_AGVS):
    agv = AGV()
    agv.activate()
    agvs.append(agv)



ContainerGenerator().activate()
SwapperStation().activate()
ChargingStation().activate()
QueueLengthMonitor().activate()

# === RUN SIMULATION ===
env.run(till=SIM_TIME)

print("\n=== AGV STATISTICS ===")
for agv in agvs:
    print(f"{agv.name()} - Charges: {agv.charge_count}, Containers handled: {agv.containers_handled}")
    charge_monitor.tally(agv.charge_count)
    container_monitor.tally(agv.containers_handled)


# === FINAL OUTPUT ===
def print_results():
    print("\n=== SIMULATION RESULTS ===")
    print(f"Battery SOC - avg: {battery_soc_monitor.mean():.2f} %")
    print(f"Battery SOH - avg: {battery_soh_monitor.mean():.2f} %")
    print(f"Charging Time - avg: {charging_time_monitor.mean()/60:.2f} min")
    print(f"AGV Idle Time - avg: {agv_idle_time_monitor.mean()/60:.2f} min")
    print(f"Container Delivery Time - avg: {container_delivery_time_monitor.mean()/60:.2f} min")
    print(f"Battery Queue - avg length: {battery_queue_monitor.mean():.2f}")
    print(f"Container Queue - avg length: {container_queue_monitor.mean():.2f}")
    print("\n=== AVERAGE AGV STATS ===")
    print(f"Avg Charges per AGV: {charge_monitor.mean():.2f}")
    print(f"Avg Containers per AGV: {container_monitor.mean():.2f}")

print_results()

