import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import gamma

#%% Plotting the arrival interval distribution
# Parameters
mean = 1
max_val = 7

# Gamma distribution: mean = shape * scale
shape = 3  # Choose shape > 1 to ensure PDF(0) = 0
scale = mean / shape  # Solve for scale

# Generate x values
x = np.linspace(1, max_val, 1000)
# Compute Gamma PDF
y = gamma.pdf(x, a=shape, scale=scale)

# Plot
plt.plot(x, y, label='Arrival Interval Distribution', color='red')
plt.title("Arrival Interval Distribution")
plt.xlabel("Arrival Interval (days)")
plt.ylabel("Probability Density")
plt.grid(True)
plt.legend()
plt.show()

#%% Plotting the amount of containers distribution
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import gamma
# Parameters
mean = 7065
shape = 8
scale = mean / shape
max_val = 24000

# Extend x range from 0 to max
x = np.linspace(0, max_val, 1000)
y = gamma.pdf(x, a=shape, scale=scale)

# Plot
plt.plot(x, y, label='Amount of containers Distribution', color='blue')
plt.title("Amount of Containers Arriving Distribution")
plt.xlabel("# of Containers arriving")
plt.ylabel("Probability Density")
plt.grid(True)
plt.legend()
plt.show()

#%% Plotting the location distribution

# It's a uniform distribution, so we no need to show it, its literally a flat line