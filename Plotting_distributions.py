import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm

# Parameters
mean = 1
min_val = 0
max_val = 7

# Estimate standard deviation assuming 99.7% in min max
std_dev = (max_val - min_val) / 6

x = np.linspace(min_val, max_val, 1000)
y = norm.pdf(x, loc=mean, scale=std_dev)

# Plotting
plt.figure()
plt.plot(x, y, label='Arrival interval normal distribution')
plt.title('Arrival Interval Normal Distribution')
plt.xlabel('Arrival Interval (days)')
plt.ylabel('Probability Density')
plt.grid()
plt.legend()
plt.show()

