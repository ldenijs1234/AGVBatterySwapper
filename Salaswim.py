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
USE_SOC_WINDOW = False
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
SIM_TIME = 24 * 60 * 60 if TEST_MODE else 30 * 24 * 60 * 60 # 1 day or 30 days
SOC_MIN = 20 if USE_SOC_WINDOW else 5
SOC_MAX = 80 if USE_SOC_WINDOW else 100
DEGRADATION_PROFILE = [
    ((5, 15), 0.15),    # 15% capacity loss at 1200 cycles
    ((15, 25), 0.125),  # 12.5% capacity loss
    ((25, 35), 0.09),   # 9% capacity loss
    ((35, 45), 0.06),   # 6% capacity loss
    ((45, 55), 0.05),   # 5% capacity loss
    ((55, 65), 0.08),   # 8% capacity loss
    ((65, 75), 0.09),   # 9% capacity loss
    ((75, 85), 0.09),   # 9% capacity loss
    ((85, 95), 0.095),  # 9.5% capacity loss
]

# === MONITORS ===
battery_soc_monitor = sim.Monitor("Battery SOC")
battery_soh_monitor = sim.Monitor("Battery SOH")
battery_usage_monitor = sim.Monitor("Battery Usage Count")
battery_charge_cycles_monitor = sim.Monitor("Battery Charge Cycles")

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
#BatteryQueue.animate(x=100, y=300)

ContainerQueue = sim.Queue("ContainerQueue")
#ContainerQueue.animate(x=300, y=300)

SwappingQueue = sim.Queue("SwappingQueue")
#SwappingQueue.animate(x=500, y=300)

ChargingQueue = sim.Queue("ChargingQueue")
#ChargingQueue.animate(x=700, y=300)

AGVQueue = sim.Queue("IdleAGVs")
#AGVQueue.animate(x=900, y=300)

# === COMPONENT CLASSES ===
class Battery(sim.Component):
    def setup(self, soc=100):
        self.initial_capacity = BATTERY_CAPACITY
        self.capacity = self.initial_capacity
        self.energy = soc / 100 * self.capacity
        self.soh = 100  # State of Health (percentage of initial capacity)
        self.charge_cycles = 0
        self.usage_count = 0
        self.total_energy_delivered = 0
        self.soc_history = []  # Track SOC at each charge cycle
        
        # Track cycles in each SOC range for degradation calculation
        self.cycles_in_range = {f"{low}-{high}%": 0 
                              for (low, high), _ in DEGRADATION_PROFILE}
    
    def soc(self):
        return (self.energy / self.capacity) * 100
    
    def calculate_degradation(self, start_soc, end_soc):
        """Calculate degradation based on SOC range used during charging"""
        # Find which ranges this charge cycle passed through
        ranges_used = []
        for (low, high), _ in DEGRADATION_PROFILE:
            if start_soc <= high and end_soc >= low:
                ranges_used.append((low, high))
        
        # Apply degradation proportionally for each range
        for (low, high) in ranges_used:
            range_key = f"{low}-{high}%"
            self.cycles_in_range[range_key] += 1
            
            # Find the degradation rate for this range
            degradation_rate = next(d for (l,h), d in DEGRADATION_PROFILE 
                                  if l == low and h == high)
            
            # Apply degradation (per cycle, scaled to 1200 cycles)
            capacity_loss = (degradation_rate / 1200) * self.initial_capacity
            self.capacity -= capacity_loss
            self.capacity = max(self.capacity, 0.1 * self.initial_capacity)  # Never below 10%
            
        # Update SOH
        self.soh = (self.capacity / self.initial_capacity) * 100
        battery_soh_monitor.tally(self.soh)
    
    def process(self):
        while True:
            yield self.passivate()  # Wait in BatteryQueue
            
            # Store initial SOC before charging
            start_soc = self.soc()
            start_charge = self.env.now()  # Track when charging starts
            
            # Charging process
            self.charge_cycles += 1
            energy_needed = (SOC_MAX/100 * self.capacity) - self.energy
            if energy_needed > 0:
                charging_time = (energy_needed / CHARGING_RATE) * 3600
                yield self.hold(charging_time)
                self.energy = SOC_MAX/100 * self.capacity
            
            # Calculate degradation based on SOC range
            self.calculate_degradation(start_soc, SOC_MAX)
            
            # Record statistics
            charging_time_monitor.tally(self.env.now() - start_charge)
            battery_soc_monitor.tally(self.soc())
            battery_charge_cycles_monitor.tally(self.charge_cycles)
            
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
                self.battery.usage_count += 1
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
            self.battery.total_energy_delivered += energy_used
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
                battery.activate()  # This will resume the battery's process
                yield self.hold(0)  # Allow immediate processing
            else:
                yield self.hold(1)  # Check again later

class QueueLengthMonitor(sim.Component):
    def process(self):
        while True:
            # Update monitors
            battery_queue_monitor.tally(len(BatteryQueue))
            container_queue_monitor.tally(len(ContainerQueue))
            AGV_queue_monitor.tally(len(AGVQueue))
            
            yield self.hold(60)  # record every 60 seconds


# === ENV SETUP ===
NUM_AGVS = 24
NUM_BATTERIES = 30

# create AGVs and batteries list
agvs = []
batteries = []

# Start all batteries fully charged
for _ in range(NUM_BATTERIES):
    battery = Battery(soc=100)  # Start fully charged
    batteries.append(battery)
    BatteryQueue.add(battery)  # Add to available batteries queue

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

print("\n=== BATTERY STATISTICS ===")
for i, battery in enumerate(batteries):
    print(f"{battery.name()} - Charge cycles: {battery.charge_cycles}, "
          f"Usage count: {battery.usage_count}, "
          f"Total energy delivered: {battery.total_energy_delivered:.2f} kWh, "
          f"Current SOC: {battery.soc():.1f}%")

if batteries:  # Only print averages if we have batteries
    print("\n=== AVERAGE BATTERY STATS ===")
    print(f"Avg charge cycles: {sum(b.charge_cycles for b in batteries)/len(batteries):.1f}")
    print(f"Avg usage count: {sum(b.usage_count for b in batteries)/len(batteries):.1f}")
    print(f"Total energy delivered: {sum(b.total_energy_delivered for b in batteries):.1f} kWh")
    print(f"Avg SOC across batteries: {battery_soc_monitor.mean():.1f}%")
else:
    print("No batteries found in the simulation")

print("\n=== AVERAGE AGV STATS ===")
print(f"Avg Charges per AGV: {charge_monitor.mean():.2f}")
print(f"Avg Containers per AGV: {container_monitor.mean():.2f}")
print(f"Avg Distance per AGV: {distance_monitor.mean()/1000:.2f} km")

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
    

print_results()

# env.run()