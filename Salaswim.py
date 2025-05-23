import salabim as sim
import random

sim.yieldless(False)

# === SIMULATION ENVIRONMENT ===
env = sim.Environment(trace=False, random_seed=42)
# env.animate(True)

# Coordinates for animation
# SPAWN_X, SPAWN_Y = 0, 0
# BATTERY_STATION_X, BATTERY_STATION_Y = 100, 0
# CHARGING_STATION_X, CHARGING_STATION_Y = 200, 0
# CONTAINER_PICKUP_X, CONTAINER_PICKUP_Y = 0, 100
# CONTAINER_DELIVERY_X, CONTAINER_DELIVERY_Y = 200, 100

# sim.AnimateRectangle(
#     spec=(300, 150),
#     x=0, y=0,
#     fillcolor='lightgray',
#     layer=-2
# )
# sim.AnimateText(text="Battery Station", x=BATTERY_STATION_X, y=BATTERY_STATION_Y + 10, fontsize=10, textcolor='black')
# sim.AnimateText(text="Charging", x=CHARGING_STATION_X, y=CHARGING_STATION_Y + 10, fontsize=10, textcolor='black')
# sim.AnimateText(text="Pickup", x=CONTAINER_PICKUP_X, y=CONTAINER_PICKUP_Y + 10, fontsize=10, textcolor='black')
# sim.AnimateText(text="Delivery", x=CONTAINER_DELIVERY_X, y=CONTAINER_DELIVERY_Y + 10, fontsize=10, textcolor='black')

# === CONFIGURATION FLAGS ===
USE_SWAPPING = True
USE_SOC_WINDOW = True
TEST_MODE = True

# === PARAMETERS ===
CHARGING_RATE = 300  # kW
BATTERY_CAPACITY = 191  # kWh
AGV_SPEED = 25 * 1000 / 3600  # m/s
SWAPPING_TIME = 180 # seconds	
LOADING_TIME = 18 # seconds
UNLOADING_TIME = 18 # seconds
POWER_CONSUMPTION = 17 / 25  # kWh/kmh
IDLE_POWER_CONSUMPTION = 9  # kWh
SIM_TIME = 24 * 60 * 60 if TEST_MODE else 24 * 60 * 60
SOC_MIN = 20
SOC_MAX = 80 if USE_SOC_WINDOW else 100

# === MONITORS ===
battery_soc_monitor = sim.Monitor("Battery SOC")
battery_soh_monitor = sim.Monitor("Battery SOH")

battery_queue_monitor = sim.Monitor("Battery Queue Length")
container_queue_monitor = sim.Monitor("Container Queue Length")
AGV_queue_monitor = sim.Monitor("AGV Queue Length")
charging_time_monitor = sim.Monitor("Battery Charging Time")
container_delivery_time_monitor = sim.Monitor("Container Delivery Time")
agv_idle_time_monitor = sim.Monitor("AGV Idle Time")

charge_monitor = sim.Monitor("AGV Charges")
container_monitor = sim.Monitor("Containers Delivered")
distance_monitor = sim.Monitor("Distance Traveled")


# === QUEUES ===
BatteryQueue = sim.Queue("AvailableBatteries")
BatteryQueue.animate(x=100, y=300)

ContainerQueue = sim.Queue("ContainerQueue")
ContainerQueue.animate(x=300, y=300)

SwappingQueue = sim.Queue("SwappingQueue")
SwappingQueue.animate(x=500, y=300)

ChargingQueue = sim.Queue("ChargingQueue")
ChargingQueue.animate(x=700, y=300)

AGVQueue = sim.Queue("IdleAGVs")
AGVQueue.animate(x=900, y=300)

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
            yield self.passivate()  # Wait for ChargingStation to reactivate us
            # self.animate("🔋")
            start = self.env.now()
            duration = max(0, (SOC_MAX - self.soc()) * BATTERY_CAPACITY / CHARGING_RATE * 3600)

            yield self.hold(duration)

            self.energy = SOC_MAX / 100 * BATTERY_CAPACITY
            battery_soc_monitor.tally(self.soc())
            charging_time_monitor.tally(self.env.now() - start)

            BatteryQueue.add(self)

       
    # def charge(self):
    #     start = self.env.now()
    #     duration = max(0, (SOC_MAX - self.soc()) * self.capacity / CHARGING_RATE * 3600)
    #     yield self.hold(duration)
    #     self.energy = SOC_MAX / 100 * self.capacity
    #     charging_time_monitor.tally(self.env.now() - start)
    #     battery_soc_monitor.tally(self.soc())
    #     BatteryQueue.add(self)



class AGV(sim.Component):
    def setup(self):
        self.battery = None
        self.distance_traveled = 0  # optional tracking
        self.charge_count = 0
        self.containers_handled = 0
        # self.location = (SPAWN_X, SPAWN_Y)
        # sim.AnimateCircle(
        #     radius=5,
        #     x=SPAWN_X,
        #     y=SPAWN_Y,
        #     fillcolor='blue',
        #     text=self.name(),
        #     fontsize=8,
        #     object=self
        # )


    def move_to(self, x, y, duration=1):
        # self.animate(to_x=x, to_y=y, duration=duration)
        yield self.hold(duration)
        self.location = (x, y)

    def process(self):
        # self.animate("🚗", x=200, y=random.randint(100, 200), direction="right")
        while True:
            # Battery swap only if needed
            while self.battery is None:
                SwappingQueue.add(self)
                yield self.passivate()

                # Move to battery station (for animation)
                # yield from self.move_to(BATTERY_STATION_X, BATTERY_STATION_Y, duration=3)

                # Get a battery
                while len(BatteryQueue) == 0:
                    AGVQueue.add(self)
                    yield self.passivate()

                self.battery = BatteryQueue.pop()
                yield self.hold(SWAPPING_TIME)

            # Move to container pickup
            # yield from self.move_to(CONTAINER_PICKUP_X, CONTAINER_PICKUP_Y, duration=3)

            # Get a container
            if len(ContainerQueue) == 0:
                wait_start = self.env.now()

                AGVQueue.add(self)
                yield self.passivate()

                # On reactivation — calculate idle energy usage
                idle_duration = self.env.now() - wait_start
                agv_idle_time_monitor.tally(idle_duration)
                idle_energy_used = IDLE_POWER_CONSUMPTION * (idle_duration / 3600) # in kWh 
                self.battery.energy -= idle_energy_used
                self.battery.energy = max(0, self.battery.energy)
                battery_soc_monitor.tally(self.battery.soc())

            # Proceed with container
            container = ContainerQueue.pop()
            pickup_time = self.env.now()
            yield self.hold(LOADING_TIME)

            # Drive
            travel_distance = random.uniform(1000, 5000) # in meters 
            self.distance_traveled += travel_distance
            energy_used = POWER_CONSUMPTION / 1000 * travel_distance # kW/m * m = kWh 
            self.battery.energy -= energy_used
            self.battery.energy = max(0, self.battery.energy)
            battery_soc_monitor.tally(self.battery.soc())

            # Move to delivery point (animation)
            # yield from self.move_to(CONTAINER_DELIVERY_X, CONTAINER_DELIVERY_Y, duration=travel_distance / AGV_SPEED) 
            yield self.hold(travel_distance / AGV_SPEED)
            yield self.hold(UNLOADING_TIME)

            self.containers_handled += 1
            delivery_duration = self.env.now() - pickup_time
            container_delivery_time_monitor.tally(delivery_duration / 60) # Convert to minutes 

            # Battery check
            if self.battery.soc() < SOC_MIN:
                self.charge_count += 1
                # Move to charging station (animation)
                # yield from self.move_to(CHARGING_STATION_X, CHARGING_STATION_Y, duration=3)
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

            # Reactivate an AGV if available
            if len(AGVQueue) > 0:
                agv = AGVQueue.pop()
                agv.activate()

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
            container_queue_monitor.tally(len(ContainerQueue))
            AGV_queue_monitor.tally(len(AGVQueue))
            yield self.hold(60)  # record every 60 seconds


# === ENV SETUP ===
NUM_AGVS = 24
NUM_BATTERIES = 30

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
    print(f"{agv.name()} - Charges: {agv.charge_count}, Containers handled: {agv.containers_handled}, Distance traveled: {agv.distance_traveled/1000:.2f} km")
    charge_monitor.tally(agv.charge_count)
    container_monitor.tally(agv.containers_handled)
    distance_monitor.tally(agv.distance_traveled)

# === FINAL OUTPUT ===
def print_results():
    print("\n=== SIMULATION RESULTS ===")
    print(f"Battery SOC - avg: {battery_soc_monitor.mean():.2f} %")
    print(f"Battery SOH - avg: {battery_soh_monitor.mean():.2f} %")
    print(f"Charging Time - avg: {charging_time_monitor.mean()/60:.2f} min")
    print(f"AGV Idle Time - avg: {agv_idle_time_monitor.mean()/60:.2f} min")
    print(f"Container Delivery Time - avg: {container_delivery_time_monitor.mean():.2f} min")
    print(f"Battery Queue - avg length: {battery_queue_monitor.mean():.2f}")
    print(f"Container Queue - avg length: {container_queue_monitor.mean():.2f}")
    print(f"AGV Queue - avg length: {AGV_queue_monitor.mean():.2f}")
    print("\n=== AVERAGE AGV STATS ===")
    print(f"Avg Charges per AGV: {charge_monitor.mean():.2f}")
    print(f"Avg Containers per AGV: {container_monitor.mean():.2f}")
    print(f"Avg Distance per AGV: {distance_monitor.mean()/1000:.2f} km")

print_results()

# env.run()