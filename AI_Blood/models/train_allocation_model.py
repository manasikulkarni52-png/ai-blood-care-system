import pandas as pd
import pickle

from sklearn.ensemble import RandomForestClassifier

# Load dataset
df = pd.read_csv("allocation_data.csv")

print("Dataset Loaded")
print(df.head())

# Features
X = df[[
    'current_stock',
    'requested_units',
    'emergency_hits',
    'pending_requests',
    'eligible_donors'
]]

# Target
y = df['auto_allocate']

# Train model
model = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)

model.fit(X, y)

# Save model
with open("models/allocation_model.pkl", "wb") as f:
    pickle.dump(model, f)

print("✅ Allocation AI Model Trained Successfully")