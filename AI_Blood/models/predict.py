import pickle
import numpy as np

# Load trained model
model = pickle.load(open('models/disease_model.pkl', 'rb'))

# Load label encoder
label_encoder = pickle.load(open('models/label_encoder.pkl', 'rb'))


def predict_disease(hb, rbc, wbc, plt):
    try:
        # Prepare input for model
        data = np.array([[hb, rbc, wbc, plt]])

        print("🔍 Input Data:", data)

        # ML Prediction
        prediction = model.predict(data)

        # Convert numeric label to disease name
        disease = label_encoder.inverse_transform(prediction)[0]

        print("🧠 ML Prediction:", disease)

        # -------------------------------
        # 🔒 SAFETY RULES (Medical Logic)
        # -------------------------------

        # Normal ranges
        if (12 <= hb <= 17.5 and
            4.0 <= rbc <= 6.0 and
            4500 <= wbc <= 11000 and
            150000 <= plt <= 450000):

            disease = "Normal Health"

        # Thrombocytosis (HIGH Platelets)
        elif plt > 450000:
            disease = "Thrombocytosis"

        # Thrombocytopenia (LOW Platelets)
        elif plt < 150000:
            disease = "Thrombocytopenia"

        # Infection
        elif wbc > 11000:
            disease = "Infection"

        # Leukopenia
        elif wbc < 4000:
            disease = "Leukopenia"

        # Anemia
        elif hb < 12 or rbc < 4.0:
            disease = "Anemia"

        return disease

    except Exception as e:
        print("❌ Prediction Error:", str(e))
        return "Error in Prediction"