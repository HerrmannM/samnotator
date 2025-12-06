# Samnotator

A simple enough image anotation application for [SAM](https://github.com/facebookresearch/sam3), written in Python/Qt/PySide6, for learning purpose.
Samnotator currently only supports simple point annotations.

# Get models
Models must be downloaded separately.

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
