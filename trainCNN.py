import torch
import torch.nn as nn
import random
import CNN
from torch.utils.data import DataLoader,random_split,Subset
from torchvision import datasets, transforms
import numpy as np
import matplotlib.pyplot as plt
# import kagglehub
#
# # Download latest version
# path = kagglehub.dataset_download("phylake1337/fire-dataset")
#
# print("Path to dataset files:", path)
def main():
    random.seed(66)
    torch.manual_seed(66)
    data_transforms = transforms.Compose([
        transforms.Resize((96, 96)),
        transforms.ToTensor(),  # 这一步会归一化到 [0,1]
        transforms.Lambda(lambda x: x * 255)  # 反归一化回 [0,255]
    ])
    dataset=datasets.ImageFolder(root='./fire_dataset', transform=data_transforms)
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    indices=list(range(len(dataset)))
    random.shuffle(indices)
    train_indices=indices[:train_size]
    val_indices=indices[train_size:]
    train_dataset=Subset(dataset, train_indices)
    val_dataset = Subset(dataset, val_indices)
    train_loader = DataLoader(dataset=train_dataset, batch_size=64, shuffle=True, num_workers=0)
    val_loader = DataLoader(dataset=val_dataset, batch_size=64, shuffle=True, num_workers=0)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(device)
    model=CNN.MobileNetV3Small()
    model=model.to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
    epoch=30
    bestacc=0
    for epoch in range(epoch):
        model.train()
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
        model.eval()
        risk=0
        accuracy=0
        for images, labels in val_loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            loss = criterion(outputs, labels)
            preds = torch.argmax(outputs, dim=1)  # 取最大概率的类别
            corr_preds=(preds==labels).float().mean()
            risk+=loss.item()
            accuracy+=corr_preds.item()
        risk=risk/len(val_loader)
        accuracy=accuracy/len(val_loader)
        print(f"epoch {epoch}: risk:{risk}, acc:{accuracy}")

        if accuracy > bestacc:
            torch.save(model.state_dict(), 'CNN.pth')
            bestacc=accuracy
if __name__ == '__main__':
    main()