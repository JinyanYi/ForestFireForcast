import torch
import torch.nn as nn
class ModelWithSoftmax(torch.nn.Module):
    def __init__(self, original_model):
        super().__init__()
        self.model = original_model
        self.softmax = nn.Softmax(dim=1)

    def forward(self, x):
        return self.softmax(self.model(x))

model = torch.load("model_pruned.pth", map_location="cpu")
model_with_softmax = ModelWithSoftmax(model)
model_with_softmax.eval()
# 加载 PyTorch 剪枝后的模型


model.eval()

# 创建一个示例输入（Edge Impulse 需要静态输入尺寸）
dummy_input = torch.randn(1, 3, 96, 96)

# 导出为 ONNX
torch.onnx.export(
    model_with_softmax,
    dummy_input,
"model_with_softmax.onnx",

    opset_version=11,  # 适用于 Edge Impulse

    input_names=["input"],
    output_names=["output"]
)

print("✅ PyTorch 模型已转换为 ONNX！")
