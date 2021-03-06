import os
import sys
import time
import argparse

import cv2
import numpy as np

import ailia
import onnxruntime

# import original modules
sys.path.append('../util')
from utils import check_file_existance  # noqa: E402
from model_utils import check_and_download_models  # noqa: E402
from yolo_face import FaceLocator

# ======================
# PARAMETERS
# ======================

WEIGHT_PATH = [
    'councilGAN-glasses.onnx',
    'councilGAN-m2f_256.onnx',
    'councilGAN-anime.onnx'
]
MODEL_PATH = [
    'councilGAN-glasses.onnx.prototxt',
    'councilGAN-m2f_256.onnx.prototxt',
    'councilGAN-anime.onnx.prototxt'
]
MODEL = 0

REMOTE_PATH = "https://storage.googleapis.com/ailia-models/council-gan/"

IMAGE_PATH = 'sample.jpg'
SAVE_IMAGE_PATH = 'output.png'


# ======================
# Arguemnt Parser Config
# ======================

parser = argparse.ArgumentParser(
    description='Glasses removal, m2f and anime transformation GAN based on SimGAN'
)
parser.add_argument(
    '-i', '--input', metavar='IMAGE',
    default=IMAGE_PATH,
    help='The input image path.'
)
parser.add_argument(
    '-v', '--video', metavar='VIDEO',
    default=None,
    help='The input video path. ' +
         'If the VIDEO argument is set to 0, the webcam input will be used.'
)
parser.add_argument(
    '-s', '--savepath', metavar='SAVE_IMAGE_PATH',
    default=SAVE_IMAGE_PATH,
    help='Save path for the output image.'
)
parser.add_argument(
    '-b', '--benchmark',
    action='store_true',
    help='Running the inference on the same input 5 times ' +
         'to measure execution performance. (Cannot be used in video mode)'
)
parser.add_argument(
    '-f', '--face_recognition',
    action='store_true',
    help='Run face recognition with yolo v3 (only for glasses removal mode)'
)
parser.add_argument(
    '-d', '--dilation', metavar='DILATION',
    default=1,
    help='Dilation value for face recognition image size'
)
parser.add_argument(
    '-o', '--onnx',
    action='store_true',
    help='Run on ONNXruntime instead of Ailia'
)
parser.add_argument(
    '-g', '--glasses',
    action='store_true',
    help='Run glasses-removal mode'
)
parser.add_argument(
    '-m', '--m2f',
    action='store_true',
    help='Run male-to-female mode'
)
parser.add_argument(
    '-a', '--anime',
    action='store_true',
    help='Run anime mode'
)
args = parser.parse_args()

# ======================
# Preprocessing functions
# ======================
def preprocess(image):
    """Convert channel-first BGR image as numpy /n
    array to normalized channel-last RGB."""
    image = center_crop(image)
    size = [128, 256, 256][MODEL]
    image = cv2.resize(image, (size, size))
    # BGR to RGB
    image = image[...,::-1]
    # scale to [0,1]
    image = image/255.
    # swap channel order
    image = np.transpose(image, [2,0,1])
    # resize
    # normalize
    image = (image-0.5)/0.5
    return image.astype(np.float32)   

def center_crop(image):
    """Crop the image around the center to make square"""
    shape = image.shape[0:2]
    size = min(shape)
    return image[(shape[0]-size)//2:(shape[0]+size)//2, (shape[1]-size)//2:(shape[1]+size)//2, ...]

def square_coords(coords, dilation=1.0):
    """Make coordinates square for the network with /n
    dimension equal to the longer side * dilation, same /n
    center"""
    top, left, bottom, right = coords
    w = right-left
    h = bottom-top
    
    dim = 1 if w>h else 0
    
    new_size = int(max(w, h)*dilation)
    change_short = new_size - min(w, h)
    change_long = new_size - max(w, h)
    
    out = list(coords)
    out[0+dim] -= change_long//2
    out[1-dim] -= change_short//2
    out[2+dim] += change_long//2
    out[3-dim] += change_short//2
    
    return out

def get_slice(image, coords):
    """Get a subarray of the image using coordinates /n
    that may be outside the bounds of the image. If so, /n
    return a slice as if the image were padded in all /n
    sides with zeros."""
    padded_slice = np.zeros((coords[2]-coords[0], coords[3]-coords[1], 3))
    new_coords = np.zeros((4), dtype=np.int16)
    padded_coords = np.zeros((4), dtype=np.int16)
#     limit coords to the shape of the image, and get new coordinates relative to new padded shape for later replacement
    for dim in [0,1]:
        new_coords[0+dim] = 0 if coords[0+dim]<0 else coords[0+dim]
        new_coords[2+dim] = image.shape[0+dim] if coords[2+dim]>image.shape[0+dim] else coords[2+dim]
        padded_coords[0+dim] = new_coords[0+dim]-coords[0+dim]
        padded_coords[2+dim] = padded_coords[0+dim] + new_coords[2+dim] - new_coords[0+dim]
        
#     get the new correct slice and put it in padded array
    image_slice = image[sliceify(new_coords)]
    padded_slice[sliceify(padded_coords)] = image_slice 
    
    return padded_slice, new_coords, padded_coords

def sliceify(coords):
    """Turn a list of (top, left, bottom right) into slices for indexing."""
    return slice(coords[0], coords[2]), slice(coords[1], coords[3])

# ======================
# Postprocessing functions
# ======================
def postprocess_image(image):
    """Convert network output to channel-last 8bit unsigned integet array"""
    max_v = np.max(image)
    min_v = np.min(image)
    final_image = np.transpose((image-min_v)/(max_v-min_v)*255+0.5, (1,2,0)).round()
    out = np.clip(final_image, 0, 255).astype(np.uint8)
    return out

def replace_face(img, replacement, coords):
    """Replace a face in the input image with a transformed one."""
    img = img.copy()
    img[sliceify(coords)] = cv2.resize(replacement, (coords[3]-coords[1], coords[2]-coords[0]))
    return img

# ======================
# Main functions
# ======================
def transform_image():
    """Full transormation on a single image loaded from filepath in arguments."""
    image = cv2.imread(args.input)
    env_id = ailia.get_gpu_environment_id()
    print(f'env_id: {env_id}')
    
    if not args.onnx:
        net = ailia.Net(MODEL_PATH, WEIGHT_PATH, env_id=env_id)
    else:
        net = onnxruntime.InferenceSession(WEIGHT_PATH)
    
    if args.face_recognition:
        locator = FaceLocator()
    else:
        locator = None
        
    if args.benchmark:
        print('BENCHMARK mode')
        for i in range(5):
            start = int(round(time.time() * 1000))

            out_image = process_frame(net, locator, image)
            
            end = int(round(time.time() * 1000))
            print(f'\tailia processing time {end - start} ms')

    else:
        out_image = process_frame(net, locator, image)
    
    cv2.imwrite(args.savepath, out_image[...,::-1])
    return True


def process_frame(net, locator, image):
    """Process a single frame with preloaded network and locator"""
    if args.face_recognition and MODEL==0:
#         Run with face recognition using yolo
        out_image = image.copy()[...,::-1]
#         Get face coordinates with yolo
        face_coords = locator.get_faces(image[...,::-1])
#         Replace each set of coordinates with its glass-less transformation
        for coords in face_coords:
            coords = square_coords(coords, dilation=float(args.dilation))
            
            image_slice, coords, padded_coords = get_slice(image, coords)
            
            processed_slice = process_array(net, preprocess(image_slice))
            processed_slice = processed_slice[sliceify(padded_coords)]
            out_image = replace_face(out_image, processed_slice, coords)
        
    else:
        out_image = process_array(net, preprocess(image))
        
    return out_image
 
def process_array(net, img):
    """Apply network to a correctly scaled and centered image """
    if not args.onnx:
        print('Start inference...')
        preds_ailia = postprocess_image(net.predict(img[None,...])[0])
    else:
        # teporary onnxruntime mode
        print('Start inference in onnxruntime mode...')
        inputs = [i.name for i in net.get_inputs()]
        outputs = [o.name for o in net.get_outputs()]

        data = [img[None,...]] 
        out = net.run(outputs, {i: data for i, data in zip(inputs, data)})

        preds_ailia = postprocess_image(out[0][0])
            
    return preds_ailia
          
def process_video():
    # net initialize
    env_id = ailia.get_gpu_environment_id()
    print(f'env_id: {env_id}')
    if args.onnx:
        net = onnxruntime.InferenceSession(WEIGHT_PATH)
    else:
        net = ailia.Net(MODEL_PATH, WEIGHT_PATH, env_id=env_id)

    if args.face_recognition:
        locator = FaceLocator()
    else:
        locator = None
        
    if args.video == '0':
        print('[INFO] Webcam mode is activated')
        capture = cv2.VideoCapture(0)
        if not capture.isOpened():
            print("[ERROR] webcamera not found")
            sys.exit(1)
    else:
        if check_file_existance(args.video):
            capture = cv2.VideoCapture(args.video)

    while(True):
        ret, frame = capture.read()
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        if not ret:
            continue
            
        img = process_frame(net, locator, frame)
       
        cv2.imshow('frame', img[...,::-1])

    capture.release()
    cv2.destroyAllWindows()
    print('Script finished successfully.')

def main():
    # check model choice, defaults to glasses-removal
    global WEIGHT_PATH
    global MODEL_PATH
    global MODEL
    
    model_choice = [args.glasses, args.m2f, args.anime]
    if sum(model_choice)>1:
        raise ValueError('Please select only one model (-g, -m, or -a)')
    elif sum(model_choice)==0:
        pass
    else:
        MODEL = np.argmax(model_choice)
    
    global WEIGHT_PATH
    global MODEL_PATH
    
    WEIGHT_PATH = WEIGHT_PATH[MODEL]
    MODEL_PATH = MODEL_PATH[MODEL]
#     print(WEIGHT_PATH, MODEL_PATH)
        
    # model files check and download
    check_and_download_models(WEIGHT_PATH, MODEL_PATH, REMOTE_PATH)
    

    if args.video is not None:
        # video mode
        process_video()
    else:
        # image mode
        transform_image()


if __name__ == '__main__':
    main()
    print('Script finished successfully.')
