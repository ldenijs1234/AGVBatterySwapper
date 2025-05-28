import salabim as sim
import random
import sys
import matplotlib.pyplot as plt
import numpy as np
import math

sim.yieldless(False)

class TextLoadingBar:
    def __init__(self, total_steps, description="Progress"):
        self.total = total_steps
        self.current = 0
        self.description = description
        self.start_time = None

    def update(self, increment=1):
        import time
        if self.start_time is None:
            self.start_time = time.time()
        self.current += increment
        progress = min(self.current / self.total, 1)
        bar_length = 50
        filled = int(bar_length * progress)
        bar = '[' + '=' * filled + ' ' * (bar_length - filled) + ']'
        elapsed = time.time() - self.start_time
        mins, secs = divmod(int(elapsed), 60)
        hours, mins = divmod(mins, 60)
        time_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
        sys.stdout.write(f"\r{self.description}: {bar} {progress:.1%} | Elapsed: {time_str}")
        sys.stdout.flush()

    def complete(self):
        print()  # New line when done

# === SIMULATION ENVIRONMENT ===
env = sim.Environment(trace=False, random_seed=42)

# === CONFIGURATION FLAGS ===
USE_SWAPPING = False
USE_SOC_WINDOW = True
TEST_MODE = False

# === ENV SETUP ===
NUM_AGVS = 84
NUM_BATTERIES = NUM_AGVS if not USE_SWAPPING else 154

# === PARAMETERS ===
CHARGING_RATE = 300  # kW
BATTERY_CAPACITY = 191  # kWh
AGV_SPEED = 20 * 1000 / 3600  # m/s (avg speed of 20 km/h)
SWAPPING_TIME = 0 if not USE_SWAPPING else 180 # seconds	
LOADING_TIME = 18 # seconds
UNLOADING_TIME = 18 # seconds
POWER_CONSUMPTION = 17 / 25  # kWh/kmh
IDLE_POWER_CONSUMPTION = 9  # kWh
SIM_TIME = 7 * 24 * 60 * 60 if TEST_MODE else 30 * 24 * 60 * 60 # 7 day or 30 days (heb een jaar gedaan)
SOC_MIN = 20 if USE_SOC_WINDOW else 5
SOC_MAX = 80 if USE_SOC_WINDOW else 100
CRANE_CYCLE_TIME = random.normalvariate(120, 60)  # 60 to 180 seconds / max of 6 cranes per ship (time to load/unload a container) .normalvariate(mean,stddev)

DEGRADATION_PROFILE = [
    ((0, 15), 0.55),    # 15% capacity loss at 1200 cycles
    ((15, 25), 0.125),  # 12.5% capacity loss
    ((25, 35), 0.09),   # 9% capacity loss
    ((35, 45), 0.06),   # 6% capacity loss
    ((45, 55), 0.05),   # 5% capacity loss
    ((55, 65), 0.08),   # 8% capacity loss
    ((65, 75), 0.09),   # 9% capacity loss
    ((75, 85), 0.09),   # 9% capacity loss
    ((85, 100), 0.55),  # 9.5% capacity loss
]
# Coordinates in meters
SWAPPING_STATION = (0, 0)
CONTAINER_PICKUP_X = 340
CONTAINER_PICKUP_RANGE = range(290, 1491, 100)  # 290m to 1490m in 100m steps (12 points)

loading_bar = TextLoadingBar(total_steps=SIM_TIME, description="Simulation Progress")

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

swap_monitor = sim.Monitor("AGV Swaps")
container_monitor = sim.Monitor("Containers Delivered")
distance_monitor = sim.Monitor("Distance Traveled")
travel_time_monitor = sim.Monitor("Travel Time")

delivery_time_monitor = sim.Monitor("Shipment Handling Time")  # Time from first container to queue empty
delivery_amount_monitor = sim.Monitor("Containers Per Shipment")
shipment_size_monitor = sim.Monitor("Shipment Sizes")
shipment_delivery_time_monitor = sim.Monitor("Shipment Delivery Times")
shipment_unloading_time_monitor = sim.Monitor("Shipment Unloading Times")

# === HOURLY QUEUE MONITORS ===
hourly_queue_data = {
    'time': [],
    'battery_queue': [],
    'container_queue': [],
    'agv_queue': [],
    'swapping_queue': [],
    'charging_queue': []
}

# Shipment tracking data structure
shipment_tracker = {
    'active_shipments': [],  # List of active shipment dictionaries
    'completed_shipments': [],  # List of completed shipments
    'total_shipments': 0,
    'last_queue_empty_time': 0
}

# === QUEUES ===
BatteryQueue = sim.Queue("AvailableBatteries")
ContainerQueue = sim.Queue("ContainerQueue")
SwappingQueue = sim.Queue("SwappingQueue")
ChargingQueue = sim.Queue("ChargingQueue")
AGVQueue = sim.Queue("IdleAGVs")

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

class AGV(sim.Component):
    def setup(self):
        self.battery = None
        self.location = SWAPPING_STATION  # Start at swapping station
        self.distance_traveled = 0
        self.swap_count = 0
        self.containers_handled = 0
        self.waiting_for_battery = False  # Track if AGV is waiting for battery

    def calculate_distance(self, from_loc, to_loc):
        """Calculate Euclidean distance between two points"""
        return ((to_loc[0]-from_loc[0])**2 + (to_loc[1]-from_loc[1])**2)**0.5
    
    def travel_to(self, destination):
        """Travel to destination and update statistics"""
        distance = self.calculate_distance(self.location, destination)
        travel_time = distance / AGV_SPEED
        
        self.distance_traveled += distance
        energy_used = POWER_CONSUMPTION / 1000 * distance # kW/m * m = kWh 
        self.battery.energy -= energy_used
        self.battery.energy = max(0, self.battery.energy)
        self.battery.total_energy_delivered += energy_used
        battery_soc_monitor.tally(self.battery.soc())
        self.location = destination
        
        yield self.hold(travel_time)  # Simulate travel time
        distance_monitor.tally(distance)
        travel_time_monitor.tally(travel_time)

    def process(self):
        while True:
            # Battery swap only if needed
            if self.battery is None or self.battery.soc() < SOC_MIN:
                if self.battery is not None:
                    # Travel to swapping station if not already there
                    if self.location != SWAPPING_STATION:
                        yield from self.travel_to(SWAPPING_STATION)
                    # Send old battery to charging
                    ChargingQueue.add(self.battery)
                    self.battery = None
                    self.swap_count += 1 if USE_SWAPPING else 0

                # Wait for a new battery
                self.waiting_for_battery = True
                SwappingQueue.add(self)
                yield self.passivate()
                
                # Get a battery (this should be guaranteed by SwapperStation)
                if len(BatteryQueue) > 0:
                    self.battery = BatteryQueue.pop()
                    self.battery.usage_count += 1
                    yield self.hold(SWAPPING_TIME)
                    self.waiting_for_battery = False
                else:
                    # This shouldn't happen with proper SwapperStation logic
                    continue

            # Now we have a good battery, look for containers
            if len(ContainerQueue) == 0:
                # No containers available, wait
                wait_start = self.env.now()
                AGVQueue.add(self)
                yield self.passivate()

                # Calculate idle energy usage while waiting
                idle_duration = self.env.now() - wait_start
                agv_idle_time_monitor.tally(idle_duration)
                idle_energy_used = IDLE_POWER_CONSUMPTION * (idle_duration / 3600) # in kWh 
                self.battery.energy -= idle_energy_used
                self.battery.energy = max(0, self.battery.energy)
                battery_soc_monitor.tally(self.battery.soc())
                
                # After waiting, check battery again
                continue

            # Get container and deliver
            container = ContainerQueue.pop()
            pickup_time = self.env.now()

            # Travel to pickup location
            pickup_y = random.choice(CONTAINER_PICKUP_RANGE)

            pickup_point = (CONTAINER_PICKUP_X, pickup_y)
            yield from self.travel_to(pickup_point)
            yield self.hold(LOADING_TIME)

            # Travel to delivery location
            delivery_point = (
                random.uniform(300, 1300),  # X coordinate (300-1300m)
                random.uniform(250, 1000)   # Y coordinate (250-1000m)
            )
            yield from self.travel_to(delivery_point)
            yield self.hold(UNLOADING_TIME)

            self.containers_handled += 1
            delivery_duration = self.env.now() - pickup_time
            container_delivery_time_monitor.tally(delivery_duration / 60) # Convert to minutes 

            # Check if we need to swap battery or can continue
            # Loop will handle battery check at the top

class Container(sim.Component):
    def setup(self):
        self.created_at = self.env.now()

class ContainerGenerator(sim.Component):
    def process(self):
        # Container count distribution
        count_shape = 8
        count_scale = 7065 / count_shape  # = 883.125

        # Arrival interval distribution (in days)
        interval_shape = 3
        interval_scale = 1 / interval_shape  # ≈ 0.333...
       
        while True:
            # Generate number of containers from gamma distribution
            num_containers = max(1, int(random.gammavariate(count_shape, count_scale)))
            arrival_time = self.env.now()
            
            # Generate deadline based on shipment size
            MEAN_SHIPMENT_SIZE = 7064  # Your reference point
            MIN_DEADLINE = 1400  # minutes (for smallest shipments)
            MAX_DEADLINE = 7000  # minutes (for largest shipments)
            MEAN_DEADLINE = 3000  # minutes (for mean shipment size)
            
            size_ratio = num_containers / MEAN_SHIPMENT_SIZE
            
            # Linear scaling for small shipments (<7064 containers)
            if num_containers <= MEAN_SHIPMENT_SIZE:
                deadline_minutes = MIN_DEADLINE + (MEAN_DEADLINE - MIN_DEADLINE) * (size_ratio - (500/7064))
            # Linear scaling for large shipments (>7064 containers)
            else:
                deadline_minutes = MEAN_DEADLINE + (MAX_DEADLINE - MEAN_DEADLINE) * ((size_ratio - 1) / ((24000/7064) - 1))
            
            # Apply normal distribution variation around the calculated deadline
            deadline_minutes = random.normalvariate(deadline_minutes, 300)  # 300 min standard deviation
            deadline_minutes = max(MIN_DEADLINE, min(MAX_DEADLINE, deadline_minutes))
                       
            # Create shipment record
            shipment = {
                'id': shipment_tracker['total_shipments'],
                'size': num_containers,
                'arrival_time': arrival_time,
                'unloading_start_time': arrival_time,
                'unloading_completion_time': None,
                'unloading_duration': None,
                'unloading_completed': False,
                'delivery_time': None,
                'completion_time': None,
                'deadline_minutes': deadline_minutes,
                'deadline_time': arrival_time + (deadline_minutes * 60),
                'is_on_time': None,  # Will be determined when completed
                'is_overdue': None
            }
            
            # Add to tracking
            shipment_tracker['active_shipments'].append(shipment)
            shipment_tracker['total_shipments'] += 1
            
            # Record shipment size
            shipment_size_monitor.tally(num_containers)

            # Calculate how many full 6-container cycles are needed
            cycles = math.ceil(num_containers / 6)  # 6 containers per cycle
            containers_added = 0

            # Simulate the crane loading containers
            for cycle in range(cycles):
                # Generate cycle time with normal distribution
                cycle_time = CRANE_CYCLE_TIME
                
                # Hold for the cycle time before adding the next batch
                if cycle > 0:  # No wait before first batch
                    yield self.hold(cycle_time)

                remaining = num_containers - cycle * 6
                to_unload = min(remaining, 6)  # Unload up to 6 containers per cycle

                # Add containers to queue and immediately reactivate AGVs
                for _ in range(to_unload):
                    ContainerQueue.add(Container())
                    container_queue_monitor.tally(len(ContainerQueue))
                    containers_added += 1
            
            # Mark shipment unloading as completed
            unloading_completion_time = self.env.now()
            shipment['unloading_completion_time'] = unloading_completion_time
            shipment['unloading_duration'] = unloading_completion_time - shipment['unloading_start_time']
            shipment['unloading_completed'] = True
            
            # Record unloading duration in a new monitor
            shipment_unloading_time_monitor.tally(shipment['unloading_duration'] / 60)  # Convert to minutes
            
            # Time between shipments
            interval_days = max(0.01, random.gammavariate(interval_shape, interval_scale))
            interval_seconds = interval_days * 24 * 60 * 60
            yield self.hold(interval_seconds)

class SwapperStation(sim.Component):
    def process(self):
        while True:
            if len(SwappingQueue) > 0 and len(BatteryQueue) > 0:
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

            # Update loading bar every minute
            loading_bar.update(60)

            yield self.hold(60)  # record every 60 seconds

class HourlyQueueMonitor(sim.Component):
    def process(self):
        while True:
            # Record queue lengths every hour
            current_time_hours = self.env.now() / 3600  # Convert seconds to hours
            
            hourly_queue_data['time'].append(current_time_hours)
            hourly_queue_data['battery_queue'].append(len(BatteryQueue))
            hourly_queue_data['container_queue'].append(len(ContainerQueue))
            hourly_queue_data['agv_queue'].append(len(AGVQueue))
            hourly_queue_data['swapping_queue'].append(len(SwappingQueue))
            hourly_queue_data['charging_queue'].append(len(ChargingQueue))
            
            yield self.hold(3600)  # Wait 1 hour (3600 seconds)

class ShipmentTracker(sim.Component):
    """Tracks shipment unloading times and container queue dynamics"""
    def setup(self):
        self.queue_was_empty = True  # Start assuming queue is empty
        self.last_check_time = 0
    
    def process(self):
        while True:
            current_queue_length = len(ContainerQueue)
            current_time = self.env.now()
            
            # Check if queue just became empty
            if current_queue_length == 0 and not self.queue_was_empty:
                self.queue_was_empty = True
                shipment_tracker['last_queue_empty_time'] = current_time
                
                # Complete all active shipments that have finished unloading
                completed_shipments = []
                for shipment in shipment_tracker['active_shipments']:
                    # Only complete shipments that have finished unloading
                    if shipment.get('unloading_completed', False):
                        delivery_time = current_time - shipment['arrival_time']
                        shipment['delivery_time'] = delivery_time
                        shipment['completion_time'] = current_time
                        
                        # Check if shipment was delivered on time
                        if current_time <= shipment['deadline_time']:
                            shipment['is_on_time'] = True
                            shipment['is_overdue'] = False
                        else:
                            shipment['is_on_time'] = False
                            shipment['is_overdue'] = True
                        
                        # Record in monitors
                        shipment_delivery_time_monitor.tally(delivery_time / 3600)  # Convert to hours
                        
                        completed_shipments.append(shipment)
                
                # Move completed shipments
                shipment_tracker['completed_shipments'].extend(completed_shipments)
                # Remove completed shipments from active list
                shipment_tracker['active_shipments'] = [
                    s for s in shipment_tracker['active_shipments'] 
                    if s not in completed_shipments
                ]
                
            # Check if queue has containers (not empty)
            elif current_queue_length > 0:
                self.queue_was_empty = False
            
            self.last_check_time = current_time
            yield self.hold(30)  # Check every 30 seconds

class AGVActivator(sim.Component):
    def process(self):
        while True:
            # Only activate AGVs if there are containers waiting
            if len(ContainerQueue) > 0:
                # Reactivate idle AGVs that are ready to work
                agvs_to_activate = []
                for agv in list(AGVQueue):
                    if (agv.battery is not None and 
                        not agv.waiting_for_battery and 
                        agv.battery.soc() > SOC_MIN):
                        agvs_to_activate.append(agv)
                
                # Activate found AGVs
                for agv in agvs_to_activate:
                    AGVQueue.remove(agv)
                    agv.activate()
            
            # Check every 30 seconds (adjust frequency as needed)
            yield self.hold(30)

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
HourlyQueueMonitor().activate()
ShipmentTracker().activate()
AGVActivator().activate()

# === RUN SIMULATION ===
env.run(till=SIM_TIME)

loading_bar.complete()

# print("\n=== AGV STATISTICS ===")
for agv in agvs:
    # print(f"{agv.name()} - Battery swaps: {agv.swap_count}, Containers handled: {agv.containers_handled}, Distance traveled: {agv.distance_traveled/1000:.2f} km")
    swap_monitor.tally(agv.swap_count)
    container_monitor.tally(agv.containers_handled)
    distance_monitor.tally(agv.distance_traveled)

# print("\n=== BATTERY STATISTICS ===")
# for i, battery in enumerate(batteries):
#     print(f"{battery.name()} - Charge cycles: {battery.charge_cycles}, "
#           f"Usage count: {battery.usage_count}, "
#           f"Total energy delivered: {battery.total_energy_delivered:.2f} kWh, "
#           f"Current SOC: {battery.soc():.1f}%")

print("\n=== AVERAGE BATTERY STATS ===")
print(f"Avg charge cycles: {sum(b.charge_cycles for b in batteries)/len(batteries):.1f}")
print(f"Avg usage count: {sum(b.usage_count for b in batteries)/len(batteries):.1f}")
print(f"Total energy delivered: {sum(b.total_energy_delivered for b in batteries):.1f} kWh")
print(f"Avg SOC across batteries: {battery_soc_monitor.mean():.1f}%")

print("\n=== AVERAGE AGV STATS ===")
print(f"Avg Swaps per AGV: {swap_monitor.mean():.2f}")
print(f"Avg Containers per AGV: {container_monitor.mean():.2f}")
print(f"Avg Distance per AGV: {distance_monitor.mean()/1000:.2f} km")

# === SIMULATION RESULTS ===
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

def print_shipment_statistics():
    print("\n=== SHIPMENT STATISTICS ===")
    print(f"Total Shipments: {shipment_tracker['total_shipments']}")
    completed_count = len(shipment_tracker['completed_shipments'])
    active_count = len(shipment_tracker['active_shipments'])
    print(f"Completed Shipments: {completed_count}")
    print(f"Active Shipments: {active_count}")
        
    if shipment_size_monitor.number_of_entries() > 0:
        print(f"Average Shipment Size: {shipment_size_monitor.mean():.2f} containers")
        shipment_sizes = shipment_size_monitor.x()  # Call the method to get the list
        print(f"Max Shipment Size: {max(shipment_sizes):.0f} containers")
        print(f"Min Shipment Size: {min(shipment_sizes):.0f} containers")
        
    if shipment_delivery_time_monitor.number_of_entries() > 0:
        print(f"Average Shipment Delivery Time: {shipment_delivery_time_monitor.mean():.2f} hours")
        delivery_times = shipment_delivery_time_monitor.x()  # Call the method to get the list
        print(f"Max Shipment Delivery Time: {max(delivery_times):.2f} hours")
        print(f"Min Shipment Delivery Time: {min(delivery_times):.2f} hours")
    """Analyze shipment patterns and overlaps"""
    if not shipment_tracker['completed_shipments']:
        print("No completed shipments to analyze.")
        return
    
    completed = shipment_tracker['completed_shipments']
     
    # Calculate overlaps
    overlapping_shipments = 0
    for i, shipment in enumerate(completed):
        # Check if this shipment overlapped with the next one
        if i < len(completed) - 1:
            next_shipment = completed[i + 1]
            if next_shipment['arrival_time'] < shipment['completion_time']:
                overlapping_shipments += 1
    
    print(f"Shipments with Overlaps: {overlapping_shipments} out of {len(completed)} ({overlapping_shipments/len(completed)*100:.1f}%)")
        
    # Additional detailed statistics
    if shipment_tracker['completed_shipments']:
        print("\n=== DETAILED SHIPMENT ANALYSIS ===")
        completed = shipment_tracker['completed_shipments']
            
        total_containers = sum(s['size'] for s in completed)
        avg_size = total_containers / len(completed)
        avg_delivery_hours = sum(s['delivery_time'] for s in completed) / len(completed) / 3600
            
        print(f"Total Containers Delivered in Completed Shipments: {total_containers}")
        print(f"Average Containers per Completed Shipment: {avg_size:.2f}")
        print(f"Average Delivery Time for Completed Shipments: {avg_delivery_hours:.2f} hours")
            
        # Show some examples of recent shipments
        print("\n=== RECENT COMPLETED SHIPMENTS (Last 5) ===")
        for shipment in completed[-5:]:
            status = "ON TIME" if shipment['is_on_time'] else f"OVERDUE (delay: {(shipment['completion_time'] - shipment['deadline_time']) / 60:.1f} min)"
            print(
                f"Shipment {shipment['id']}: {shipment['size']} containers, "
                f"{(shipment['delivery_time'] / 3600):.1f} hours delivery, "
                f"deadline: {(shipment['deadline_minutes'] / 60):.1f} hours, {status}"
            )

def print_delivery_performance():
    completed_shipments = shipment_tracker['completed_shipments']
    
    if not completed_shipments:
        print("\n=== DELIVERY PERFORMANCE ===\nNo shipments completed yet")
        return
    
    # Calculate performance metrics
    on_time = [s for s in completed_shipments if s['is_on_time']]
    overdue = [s for s in completed_shipments if s['is_overdue']]
    
    total_shipments = len(completed_shipments)
    on_time_pct = (len(on_time) / total_shipments) * 100 if total_shipments > 0 else 0
    overdue_pct = 100 - on_time_pct
    
    avg_delay = (sum((s['completion_time'] - s['deadline_time']) / 60 
                for s in overdue) / len(overdue)) if overdue else 0
    
    # Print performance summary
    print("\n=== DELIVERY PERFORMANCE ===")
    print(f"Shipments Delivered ON TIME: {len(on_time)} ({on_time_pct:.1f}%)")
    print(f"Shipments Delivered OVERDUE: {len(overdue)} ({overdue_pct:.1f}%)")
    print(f"Average Delay for Overdue Shipments: {avg_delay:.1f} minutes")

def plot_queue_lengths():
    # Convert time to days for better readability
    time_days = np.array(hourly_queue_data['time']) / 24
    
    # Also create a separate figure with normalized view (log scale for container queue)
    plt.figure(figsize=(15, 8))
    
    plt.subplot(2, 1, 1)
    plt.plot(time_days, hourly_queue_data['container_queue'], 'b-', linewidth=2, label='Container Queue')
    plt.title('Container Queue Length (Linear Scale)')
    plt.xlabel('Time (days)')
    plt.ylabel('Queue Length')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.subplot(2, 1, 2)
    # Plot other queues without container queue for better visibility
    plt.plot(time_days, hourly_queue_data['battery_queue'], 'g-', label='Battery Queue', linewidth=2)
    plt.plot(time_days, hourly_queue_data['agv_queue'], 'r-', label='AGV Queue', linewidth=2)
    plt.plot(time_days, hourly_queue_data['swapping_queue'], 'orange', label='Swapping Queue', linewidth=2)
    plt.plot(time_days, hourly_queue_data['charging_queue'], 'purple', label='Charging Queue', linewidth=2)
    plt.title('Other Queue Lengths (Excluding Container Queue)')
    plt.xlabel('Time (days)')
    plt.ylabel('Queue Length')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.show()

# === CALL ALL OUTPUT FUNCTIONS IN ORDER ===
print_results()
print_shipment_statistics()
print_delivery_performance()

input("\nPress Enter to view queue plots...")

# Then show plots
plot_queue_lengths()

# Print some statistics about the queues
# print("\n=== QUEUE STATISTICS ===")
# if hourly_queue_data['time']:
#     print(f"Container Queue - avg: {np.mean(hourly_queue_data['container_queue']):.1f}, max: {np.max(hourly_queue_data['container_queue'])}")
#     print(f"Battery Queue - avg: {np.mean(hourly_queue_data['battery_queue']):.1f}, max: {np.max(hourly_queue_data['battery_queue'])}")
#     print(f"AGV Queue - avg: {np.mean(hourly_queue_data['agv_queue']):.1f}, max: {np.max(hourly_queue_data['agv_queue'])}")
#     print(f"Swapping Queue - avg: {np.mean(hourly_queue_data['swapping_queue']):.1f}, max: {np.max(hourly_queue_data['swapping_queue'])}")
#     print(f"Charging Queue - avg: {np.mean(hourly_queue_data['charging_queue']):.1f}, max: {np.max(hourly_queue_data['charging_queue'])}")

