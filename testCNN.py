import random
import torch
import torch.nn as nn
import matplotlib.pyplot as plt
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
import CNN
from PIL import Image
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model=torch.load("model_pruned.pth", map_location=device)
model.to(device)# 加载训练好的权重
model.eval()  # 切换到推理模式

# 【3】 定义与训练时一致的 transforms
data_transforms = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
transforms.Lambda(lambda x: x * 255)
])

# 【4】 读取要预测的图片 (这里假设路径为 "./test_images/test1.jpg")
img_path = "./simulate/5.jpg"
img = Image.open(img_path).convert('RGB')  # 转为RGB三通道, 确保一致
# 可视化查看原图(可选)
plt.imshow(img)
plt.title("Original Image")
plt.show()

# 【5】 对图像做预处理
input_tensor = data_transforms(img)  # [C, H, W]张量
# 【6】 增加batch维度 [1, C, H, W]
input_tensor = input_tensor.unsqueeze(0).to(device)

# 【7】 前向推理
with torch.no_grad():
    output = model(input_tensor)  # shape: [1,1]
    output = torch.argmax(output, dim=1)  # 取最大概率的类别
 # -> 标量 logit




# 你也可以根据类别名称做个映射:
label_name = "No Fire" if output == 1 else "Fire"
print(f"Final prediction: {label_name}")