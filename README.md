# Salmon Computer Vision Project

This repository contains several tools and utilities to assist in training
salmon counting automation tools. Two major categories include video-based
enumeration and sonar-based enumeration.

## Video-based

The current enumeration strategy is using two computer vision models:
multi-object tracking (MOT) and object detection. We use
[ByteTrack](https://github.com/Salmon-Computer-Vision/ByteTrack.git) for MOT
and [YOLOv6](https://github.com/meituan/YOLOv6), respectively.

### Dataset

* Full dataset
  ([Dropbox](https://www.dropbox.com/sh/xv8i6k0hzo5jppn/AADBypR1zchux30gjUKGd4dLa?dl=0))
  of ~100 GB each for MOT and object detection.

It includes individual frame images and labels in the required format for
ByteTrack and YOLOv6. They could be easily converted to other similar formats
either manually or with
[Datumaro](https://github.com/openvinotoolkit/datumaro).

* Labels only ([GitHub
  repo](https://github.com/KamiCreed/salmon-count-labels.git)).

These annotations are in "CVAT for Video 1.1" format and include tags that
specify male/female, injuries, etc. It includes the Kitwanga River and Bear
Creek River bounding box annotations with no images. The conversion script is
in the `utils` folder (`utils/datum_create_dataset.py`), requiring
[Datumaro](https://github.com/openvinotoolkit/datumaro) to run. Refer to the
[this documentation](utils/README.md) for more details.


### Training Steps

Trained on a Ubuntu 20.04 [Lambda
Scalar](https://lambdalabs.com/products/scalar) system with 4 A5000 GPUs.

#### Multi-Object Tracker (MOT)

The current framework uses ByteTrack to track individual salmon for counting.

The following steps are for Ubuntu 20.04:

Clone our version of the ByteTrack repo:
```bash
git clone https://github.com/Salmon-Computer-Vision/ByteTrack.git
```

Follow either the docker install or host machine install in the [ByteTrack
documentation](https://github.com/Salmon-Computer-Vision/ByteTrack/blob/main/README.md)
to install all the requirements to run ByteTrack.

Download the `bytetrack_salmon.tar.gz` dataset from the above Dropbox link.

Extract it and put the `salmon` folder in the `datasets` folder.
```bash
tar xzvf bytetrack_salmon.tar.gz
mv salmon datasets
```

Download the pretrained model YOLOX nano at their [model
zoo](https://github.com/Megvii-BaseDetection/YOLOX/tree/0.1.0).

Place the pretrained model in the `pretrained` folder. The path should be
`pretrained/yolox_nano.pth`.

Run the training either inside the docker container or on the host machine:
```bash
python3 tools/train.py -f exps/example/mot/yolox_nano_salmon.py -d 4 -b 48 --fp16 -o -c pretrained/yolox_nano.pth
```

If you canceled the training in the middle, you can resume from a checkpoint
with the following command:
```bash
python3 tools/train.py -f exps/example/mot/yolox_nano_salmon.py -d 4 -b 48 --fp16 -o --resume
```

Once finished, the final outputs will be in `YOLOX_outputs/yolox_nano_salmon/`
where `best_ckpt.pth.tar` would be the checkpoint with the highest validation
mAP score.

#### Object Detector

```bash
python -m torch.distributed.launch --nproc_per_node 4 tools/train.py --epoch 100 --batch 512 --conf configs/yolov6n_finetune.py --eval-interval 2 --data data/combined_bear-kitwanga.yaml --device 0,1,2,3
```

## Sonar-based

Convert ARIS sonar files to videos with `pyARIS` using the Python 3 script
`./extract_aris/aris_to_video.py`.
