import torch
import torch.nn as nn
import torch.nn.utils.prune as prune
from torch.utils.data import DataLoader, random_split,Subset
from torchvision import datasets, transforms
import CNN
import torch_pruning as tp
import random
model = CNN.MobileNetV3Small()
model.load_state_dict(torch.load("CNN.pth", weights_only=True))
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.to(device)


prune_params = {
    "p_init": 0.0,
    "p_final": 0.8,
    "t_start": 3,
    "t_end": 25,
}

# 记录已经剪枝的比例
pruned_so_far = 0.0
best_acc = 0.0

def compute_prune_rate(epoch, prune_params):

    global pruned_so_far
    if epoch < prune_params["t_start"]:
        return 0.0
    elif epoch > prune_params["t_end"]:
        return 0.0  #
    else:
        total_target = prune_params["p_final"]
        increment = (total_target - pruned_so_far) / (prune_params["t_end"] - epoch + 1)
        return increment



def gradual_prune(model, prune_ratio,puntime):
    """ Torch-Pruning 1.5.1"""
    example_inputs = torch.randn(1, 3, 224, 224).to(device)
    imp = tp.importance.MagnitudeImportance(p=2, group_reduction='mean')
    ignored_layers = []
    for m in model.modules():
        if isinstance(m, torch.nn.Linear) and m.out_features == 2:
            ignored_layers.append(m)
            print("find fc layer")# DO NOT prune the final classifier!
    iterative_steps = puntime
    pruner = tp.pruner.MagnitudePruner(
        model,
        example_inputs,
        global_pruning=False,  # If False, a uniform ratio will be assigned to different layers.
        importance=imp,  # importance criterion for parameter selection
        iterative_steps=iterative_steps,  # the number of iterations to achieve target ratio
        pruning_ratio=prune_ratio,  # remove 50% channels, ResNet18 = {64, 128, 256, 512} => ResNet18_Half = {32, 64, 128, 256}
        ignored_layers=ignored_layers,
    )
    pruner.step()

    global pruned_so_far
    pruned_so_far = pruned_so_far + (1 - pruned_so_far) * prune_ratio



def hard_prune(model,epo):

    new_optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    return new_optimizer



random.seed(66)
torch.manual_seed(66)

optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
criterion = nn.CrossEntropyLoss()
epochs = 50
example_input = torch.randn(1, 3, 96, 96).to(device)

data_transforms = transforms.Compose([
    transforms.Resize((96, 96)),
    transforms.ToTensor(),
transforms.Lambda(lambda x: x * 255)
])

# 加载数据集
dataset = datasets.ImageFolder(root='./fire_dataset', transform=data_transforms)
train_size = int(0.8 * len(dataset))
val_size = len(dataset) - train_size
indices = list(range(len(dataset)))
random.shuffle(indices)
train_indices = indices[:train_size]
val_indices = indices[train_size:]
train_dataset = Subset(dataset, train_indices)
val_dataset = Subset(dataset, val_indices)
train_loader = DataLoader(dataset=train_dataset, batch_size=64, shuffle=True)
val_loader = DataLoader(dataset=val_dataset, batch_size=64, shuffle=True)

# 训练循环
for epoch in range(epochs):
    model.train()

    # 计算当前增量剪枝比例
    prune_ratio = compute_prune_rate(epoch, prune_params)




    if epoch <= prune_params["t_end"]:
        gradual_prune(model, prune_ratio,3)
        optimizer=hard_prune(model, epoch)  # ✅ 硬剪枝，同时清空优化器状态
    elif epoch <= 40:
        for param_group in optimizer.param_groups:
            param_group["lr"] = 1e-3
    elif epoch <= 45:
        for param_group in optimizer.param_groups:
            param_group["lr"] = 1e-4
    else :
        for param_group in optimizer.param_groups:
            param_group["lr"] = 1e-5

    for images, labels in train_loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

    # 评估
    model.eval()
    risk = 0
    accuracy = 0
    with torch.no_grad():
        for images, labels in val_loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            loss = criterion(outputs, labels)
            preds =torch.argmax(outputs, dim=1)
            corr_preds = (preds == labels).float().mean()
            risk += loss.item()
            accuracy += corr_preds.item()
    risk /= len(val_loader)
    accuracy /= len(val_loader)
    print(f"epoch {epoch}: risk:{risk}, acc:{accuracy}")
    print(f"Epoch {epoch}: Incremental Prune Ratio = {prune_ratio:.4f}, Total Pruned = {pruned_so_far:.4f}")
    if epoch > prune_params["t_end"] and accuracy > best_acc:
        best_acc = accuracy
        torch.save(model, "model_pruned.pth")  # ✅ 只保存最高准确率的模型
        print(f"✅ 最高准确率 {best_acc:.4f}，已保存 best_model.pth")
print("✅ 剪枝训练完成！")
