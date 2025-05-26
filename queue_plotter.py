import matplotlib.pyplot as plt
import numpy as np

class QueuePlotter:
    def __init__(self):
        self.hourly_queue_data = {
            'time': [],
            'battery_queue': [],
            'container_queue': [],
            'agv_queue': [],
            'swapping_queue': [],
            'charging_queue': []
        }
    
    def record_queue_lengths(self, current_time_hours, battery_queue, container_queue, 
                           agv_queue, swapping_queue, charging_queue):
        """Record queue lengths at a specific time point"""
        self.hourly_queue_data['time'].append(current_time_hours)
        self.hourly_queue_data['battery_queue'].append(battery_queue)
        self.hourly_queue_data['container_queue'].append(container_queue)
        self.hourly_queue_data['agv_queue'].append(agv_queue)
        self.hourly_queue_data['swapping_queue'].append(swapping_queue)
        self.hourly_queue_data['charging_queue'].append(charging_queue)
    
    def plot_queue_lengths(self):
        """Create comprehensive plots of all queue lengths over time"""
        if not self.hourly_queue_data['time']:
            print("No queue data available for plotting")
            return
            
        # Convert time to days for better readability
        time_days = np.array(self.hourly_queue_data['time']) / 24
        
        # Create main subplot figure
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('Queue Lengths Over Time', fontsize=16)
        
        # Container Queue
        axes[0, 0].plot(time_days, self.hourly_queue_data['container_queue'], 'b-', linewidth=2)
        axes[0, 0].set_title('Container Queue Length')
        axes[0, 0].set_xlabel('Time (days)')
        axes[0, 0].set_ylabel('Queue Length')
        axes[0, 0].grid(True, alpha=0.3)
        
        # Battery Queue
        axes[0, 1].plot(time_days, self.hourly_queue_data['battery_queue'], 'g-', linewidth=2)
        axes[0, 1].set_title('Battery Queue Length')
        axes[0, 1].set_xlabel('Time (days)')
        axes[0, 1].set_ylabel('Queue Length')
        axes[0, 1].grid(True, alpha=0.3)
        
        # AGV Queue
        axes[0, 2].plot(time_days, self.hourly_queue_data['agv_queue'], 'r-', linewidth=2)
        axes[0, 2].set_title('AGV Queue Length')
        axes[0, 2].set_xlabel('Time (days)')
        axes[0, 2].set_ylabel('Queue Length')
        axes[0, 2].grid(True, alpha=0.3)
        
        # Swapping Queue
        axes[1, 0].plot(time_days, self.hourly_queue_data['swapping_queue'], 'orange', linewidth=2)
        axes[1, 0].set_title('Swapping Queue Length')
        axes[1, 0].set_xlabel('Time (days)')
        axes[1, 0].set_ylabel('Queue Length')
        axes[1, 0].grid(True, alpha=0.3)
        
        # Charging Queue
        axes[1, 1].plot(time_days, self.hourly_queue_data['charging_queue'], 'purple', linewidth=2)
        axes[1, 1].set_title('Charging Queue Length')
        axes[1, 1].set_xlabel('Time (days)')
        axes[1, 1].set_ylabel('Queue Length')
        axes[1, 1].grid(True, alpha=0.3)
        
        # Combined plot
        axes[1, 2].plot(time_days, self.hourly_queue_data['container_queue'], 'b-', label='Container Queue', alpha=0.8)
        axes[1, 2].plot(time_days, self.hourly_queue_data['battery_queue'], 'g-', label='Battery Queue', alpha=0.8)
        axes[1, 2].plot(time_days, self.hourly_queue_data['agv_queue'], 'r-', label='AGV Queue', alpha=0.8)
        axes[1, 2].plot(time_days, self.hourly_queue_data['swapping_queue'], 'orange', label='Swapping Queue', alpha=0.8)
        axes[1, 2].plot(time_days, self.hourly_queue_data['charging_queue'], 'purple', label='Charging Queue', alpha=0.8)
        axes[1, 2].set_title('All Queues Combined')
        axes[1, 2].set_xlabel('Time (days)')
        axes[1, 2].set_ylabel('Queue Length')
        axes[1, 2].legend()
        axes[1, 2].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()
        
        # Create normalized view figure
        self._plot_normalized_view(time_days)
    
    def _plot_normalized_view(self, time_days):
        """Create normalized plots separating container queue from others"""
        plt.figure(figsize=(15, 8))
        
        plt.subplot(2, 1, 1)
        plt.plot(time_days, self.hourly_queue_data['container_queue'], 'b-', linewidth=2, label='Container Queue')
        plt.title('Container Queue Length (Linear Scale)')
        plt.xlabel('Time (days)')
        plt.ylabel('Queue Length')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        plt.subplot(2, 1, 2)
        # Plot other queues without container queue for better visibility
        plt.plot(time_days, self.hourly_queue_data['battery_queue'], 'g-', label='Battery Queue', linewidth=2)
        plt.plot(time_days, self.hourly_queue_data['agv_queue'], 'r-', label='AGV Queue', linewidth=2)
        plt.plot(time_days, self.hourly_queue_data['swapping_queue'], 'orange', label='Swapping Queue', linewidth=2)
        plt.plot(time_days, self.hourly_queue_data['charging_queue'], 'purple', label='Charging Queue', linewidth=2)
        plt.title('Other Queue Lengths (Excluding Container Queue)')
        plt.xlabel('Time (days)')
        plt.ylabel('Queue Length')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()
    
    def print_queue_statistics(self):
        """Print statistical summary of queue lengths"""
        print("\n=== QUEUE STATISTICS ===")
        if self.hourly_queue_data['time']:
            print(f"Container Queue - avg: {np.mean(self.hourly_queue_data['container_queue']):.1f}, max: {np.max(self.hourly_queue_data['container_queue'])}")
            print(f"Battery Queue - avg: {np.mean(self.hourly_queue_data['battery_queue']):.1f}, max: {np.max(self.hourly_queue_data['battery_queue'])}")
            print(f"AGV Queue - avg: {np.mean(self.hourly_queue_data['agv_queue']):.1f}, max: {np.max(self.hourly_queue_data['agv_queue'])}")
            print(f"Swapping Queue - avg: {np.mean(self.hourly_queue_data['swapping_queue']):.1f}, max: {np.max(self.hourly_queue_data['swapping_queue'])}")
            print(f"Charging Queue - avg: {np.mean(self.hourly_queue_data['charging_queue']):.1f}, max: {np.max(self.hourly_queue_data['charging_queue'])}")
        else:
            print("No queue data available for statistics")
    
    def plot_individual_queue(self, queue_name, color='blue', save_path=None):
        """Plot a single queue over time"""
        if queue_name not in self.hourly_queue_data or not self.hourly_queue_data['time']:
            print(f"No data available for {queue_name}")
            return
            
        time_days = np.array(self.hourly_queue_data['time']) / 24
        
        plt.figure(figsize=(12, 6))
        plt.plot(time_days, self.hourly_queue_data[queue_name], color=color, linewidth=2)
        plt.title(f'{queue_name.replace("_", " ").title()} Length Over Time')
        plt.xlabel('Time (days)')
        plt.ylabel('Queue Length')
        plt.grid(True, alpha=0.3)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        plt.show()
    
    def export_data_to_csv(self, filename='queue_data.csv'):
        """Export queue data to CSV file"""
        import pandas as pd
        
        if not self.hourly_queue_data['time']:
            print("No data to export")
            return
            
        df = pd.DataFrame(self.hourly_queue_data)
        df['time_days'] = df['time'] / 24
        df.to_csv(filename, index=False)
        print(f"Queue data exported to {filename}")
    
    def get_data_summary(self):
        """Return a dictionary with summary statistics"""
        if not self.hourly_queue_data['time']:
            return None
            
        summary = {}
        for queue_name in ['battery_queue', 'container_queue', 'agv_queue', 'swapping_queue', 'charging_queue']:
            data = self.hourly_queue_data[queue_name]
            summary[queue_name] = {
                'mean': np.mean(data),
                'max': np.max(data),
                'min': np.min(data),
                'std': np.std(data)
            }
        
        return summary