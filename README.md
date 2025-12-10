# Samnotator

A simple enough image anotation application for [SAM](https://github.com/facebookresearch/sam3), written in Python/Qt/PySide6, for learning purpose.
Samnotator currently only supports simple point annotations.

<p align="center">
  <img src="https://github.com/user-attachments/assets/82cde6fd-165c-4578-a14e-f0edd8a883f1" alt="Samnotator main UI" width="45%"/>
  <img src="https://github.com/user-attachments/assets/66793388-1960-4180-aebd-e461722180fa" alt="Annotation result example" width="45%"/>
</p>


<p align="center">
  <img src="https://github.com/user-attachments/assets/11e8ee9c-5e6b-47d3-b737-554adbc6ef8d" alt="All masks" width="45%" />
  <img src="https://github.com/user-attachments/assets/2007b04c-85be-41fc-b63f-d29c38e7888e" alt="Glaces mask" with="45%"/>
</p>

# Run

First, you need to get a model. See below.

```sh
source .venv/bin/activate
PYTHONPATH=src python -m samnotator.main --path test/20251205_140740.jpg 
```


# Get models
Models must be downloaded separately.
For now, only SAM3 is implemented.

## SAM3

Check [https://huggingface.co/facebook/sam3](https://huggingface.co/facebook/sam3).
Note that as of December 2025, the model is gated and requires access to be granted.

```sh
uv run huggingface-cli login
uv run huggingface-cli download facebook/sam3 --local-dir ./models/sam3
# Use `--local-dir-use-symlinks False` for self contained project.
# uv run huggingface-cli download facebook/sam3 --local-dir ./models/sam3 --local-dir-use-symlinks False
```

# Troubleshoting

On WSL (Windows Subsystem for Linux), you may encouter some graphics bugs.
If so, try to export:

```sh
export QT_QPA_PLATFORM=xcb
```
