# MARS

## Input

![Input](inputs/input0.jpg)

(Video from HMDB51 : https://serre-lab.clps.brown.edu/resource/hmdb-a-large-human-motion-database/)

Shape : (1, 3, duration, 112, 112))

## Output

The accuracy of each category. (HMDB51)

Shape : (1, 51)  

### usage
Automatically downloads the onnx and prototxt files on the first run.
It is necessary to be connected to the Internet while downloading.

For the sample image,
``` bash
$ python3 mars.py
```

By adding the `--video` option, you can input the video.   
If you pass `0` as an argument to VIDEO_PATH, you can use the webcam input instead of the video file.
```bash
$ python3 mars.py --video VIDEO_PATH
```

## Reference

[MARS: Motion-Augmented RGB Stream for Action Recognition](https://github.com/craston/MARS)

[HMDB: a large human motion database](https://serre-lab.clps.brown.edu/resource/hmdb-a-large-human-motion-database/)

## Framework

Pytorch

## Model Format

ONNX opset=10

## Netron

[mars.onnx.prototxt](https://lutzroeder.github.io/netron/?url=https://storage.googleapis.com/ailia-models/mars/mars.onnx.prototxt)
