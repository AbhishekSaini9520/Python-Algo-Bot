import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image
import os
from pathlib import Path

# CONFIG - PATHS FOR YOUR PROJECT
MODEL_PATH = "models/cv_hammer_multi.pth"
IMG_SIZE = 224

# Load your model metadata
checkpoint = torch.load(MODEL_PATH, map_location='cpu')
model_state = checkpoint['model_state_dict']
train_classes = checkpoint.get('train_classes', ['bearish', 'bullish', 'none'])
class_to_idx = checkpoint.get('train_class_to_idx', {0: 'bearish', 1: 'bullish', 2: 'none'})
best_val_acc = checkpoint.get('best_val_acc', 0.0)

print(f"✅ Model loaded: {best_val_acc:.1%} val accuracy")
print(f"Classes: {train_classes}")

# TRANSFORMS (same as training)
transform = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.485,0.456,0.406], [0.229,0.224,0.225])
])

# MODEL
model = models.resnet18(weights=None)  # No pretrained weights
num_f = model.fc.in_features
model.fc = nn.Linear(num_f, len(train_classes))
model.load_state_dict(model_state)
model.eval()

def predict_hammer(image_path: str, confidence_threshold: float = 0.5):
    """
    Predict hammer pattern in candlestick image
    
    Args:
        image_path: Path to PNG candlestick image
        confidence_threshold: Min confidence to make prediction
    
    Returns:
        dict: prediction, confidence, class name
    """
    # Load & preprocess image
    img = Image.open(image_path).convert('RGB')
    img_t = transform(img).unsqueeze(0)
    
    # Predict
    with torch.no_grad():
        outputs = model(img_t)
        probs = torch.nn.functional.softmax(outputs[0], dim=0)
        confidence, predicted = torch.max(probs, 0)
        predicted_class = predicted.item()
    
    class_name = train_classes[predicted_class]
    confidence_pct = confidence.item()
    
    result = {
        "class": class_name,
        "confidence": confidence_pct,
        "is_hammer": class_name != "none",
        "confidence_pct": f"{confidence_pct:.1%}"
    }
    
    if confidence_pct >= confidence_threshold:
        print(f"✅ {image_path}")
        print(f"   Prediction: {class_name} ({result['confidence_pct']})")
        return result
    else:
        print(f"❓ {image_path} - Low confidence: {result['confidence_pct']}")
        return result

# BATCH PREDICTION
def predict_folder(folder_path: str, confidence_threshold: float = 0.5):
    """Predict all images in a folder"""
    folder = Path(folder_path)
    results = []
    
    for img_path in sorted(folder.glob("*.png")):
        result = predict_hammer(str(img_path), confidence_threshold)
        results.append(result)
    
    # Summary
    hammer_count = sum(1 for r in results if r["is_hammer"])
    total = len(results)
    print(f"\n📊 Summary: {hammer_count}/{total} hammers detected ({hammer_count/total:.1%})")
    return results

# MAIN USAGE EXAMPLES
if __name__ == "__main__":
    # Single image
    predict_hammer("test_image.png")
    
    # Entire folder
    # predict_folder("data/test_images/")
    
    print("\n✅ Ready for your trading bot!")
