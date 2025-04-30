import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Load the CSV file
file_path = "ev_battery_charging_data.csv"
df = pd.read_csv(file_path)

# Display the first few rows to understand the structure
df.head()

# Set the plot style
sns.set(style="whitegrid")

# Create the plot
plt.figure(figsize=(10, 6))
sns.scatterplot(data=df, x='SOC (%)', y='Degradation Rate (%)', hue='Battery Type')

# Customize the plot
plt.title('Degradation Rate vs SOC by Battery Type')
plt.xlabel('State of Charge (%)')
plt.ylabel('Degradation Rate (%)')
plt.legend(title='Battery Type')
plt.tight_layout()
plt.show()

# Create a scatter plot of Degradation Rate vs Charging Cycles
plt.figure(figsize=(10, 6))
sns.scatterplot(data=df, x='Charging Cycles', y='Degradation Rate (%)', hue='Battery Type')

# Customize the plot
plt.title('Degradation Rate vs Charging Cycles by Battery Type')
plt.xlabel('Charging Cycles')
plt.ylabel('Degradation Rate (%)')
plt.legend(title='Battery Type')
plt.tight_layout()
plt.show()

# Let's check correlation values between degradation rate and other numerical features
correlation_matrix = df.corr(numeric_only=True)
degradation_correlations = correlation_matrix['Degradation Rate (%)'].sort_values(ascending=False)
degradation_correlations
