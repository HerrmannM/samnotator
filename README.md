# Samnotator

A simple enough image anotation application for [SAM](https://github.com/facebookresearch/sam3), written in Python/Qt/PySide6, for learning purpose.
Samnotator currently work with Promptable Visual Segmentation: points and bounding boxes.

# Examples

## Image with points (positive & negative) and bounding box

<p align="center">
  <img src="https://github.com/user-attachments/assets/29910aae-00be-4c5e-be1b-de35ce28ed61" alt="Samnotator main UI" width="45%"/>
  <img src="https://github.com/user-attachments/assets/aefeff58-4c48-49d5-92f9-221af98a4329" alt="Annotation result example" width="45%"/>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/3813be18-e2ae-4272-8fc6-2827e6e133b9" alt="All masks" width="45%" />
  <img src="https://github.com/user-attachments/assets/98f71f13-9121-4152-ae7d-4c717ae03cb9" alt="Glaces mask" width="45%"/>
</p>

## Video

<p align="center">
  <img src="https://github.com/user-attachments/assets/8a55ac60-8513-4ef0-a34e-0f3301f7f49f" alt="Video prompt" width="45%" />
  <img src="https://github.com/user-attachments/assets/586583fc-8b6c-4b9c-af73-842907d4cbe0" alt="Video gif" width="45%"/>
</p>

# Usage

First, you need to install the dependencies. We are using uv.
Then, get a model. See below.

```sh
uv sync
source .venv/bin/activate
PYTHONPATH=src python -m samnotator.main --path test/objects.jpg  # Optional path
```

Use the file menu to open a file or a directory.
Add instances with the right pan, and add annotations by clicking on the image with a selected instance.

Select a kind of model (image/video) and an implementation (for now, only SAM3 wrappers, on for each kind).
Load the model and lanch the inference.
On video mode, assumes that all the loaded frames form a video.

## Commands:

* click left/right: positive/negative point
* click & drag left: bounding box (right click gives a negative bounding box, not used for now)
* click left on item: select/move
* After selection, click on empty scene: deselect
* left/righ arrow: change frames



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
