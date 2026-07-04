import pandas as pd
import pickle
from sklearn.ensemble import RandomForestClassifier

# Load dataset (your SQL exported file)
df = pd.read_csv('shortage_data.csv')

print("Columns:", df.columns)

# Drop unnecessary columns
df = df.drop(columns=['blood_group', 'day'])

# Create label
df['shortage_occurred'] = df['current_stock'].apply(lambda x: 1 if x <= 2 else 0)

# Features
X = df[['current_stock', 'request_volume', 'emergency_hits']]

# Target
y = df['shortage_occurred']

# Train model
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X, y)

# Save model
with open('models/shortage_model.pkl', 'wb') as f:
    pickle.dump(model, f)

print("✅ Shortage Model Saved Successfully")