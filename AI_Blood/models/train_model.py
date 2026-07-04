import pandas as pd
import pickle

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

# Load dataset
df = pd.read_csv('blood_data.csv')

print("Columns:", df.columns)

# Features (must match exactly everywhere)
X = df[['hb', 'rbc', 'wbc', 'plt']]

# Target
y = df['label']

# Encode labels
label_encoder = LabelEncoder()
y_encoded = label_encoder.fit_transform(y)

# Split
X_train, X_test, y_train, y_test = train_test_split(
    X, y_encoded, test_size=0.2, random_state=42
)

# Train model
model = RandomForestClassifier(random_state=42)
model.fit(X_train, y_train)

# Accuracy
accuracy = model.score(X_test, y_test)
print("✅ Accuracy:", accuracy)

# Save model safely
with open('models/disease_model.pkl', 'wb') as f:
    pickle.dump(model, f)

# Save encoder safely
with open('models/label_encoder.pkl', 'wb') as f:
    pickle.dump(label_encoder, f)

print("✅ Model and Encoder saved successfully")