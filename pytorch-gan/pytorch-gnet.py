import sys
import time
import argparse

import numpy as np
import cv2

import ailia

sys.path.append('../util')
from model_utils import check_and_download_models  # noqa: E402


# ======================
# Parameters
# ======================
SAVE_IMAGE_PATH = 'output.png' # default value
MODEL_NAME = 'celeb' # default value

REMOTE_PATH = f'https://storage.googleapis.com/ailia-models/pytorch-gan/'

# =======================
# Arguments Parser Config
# =======================
parser = argparse.ArgumentParser(
    description='Generation of anime character faces using a GNet trained from the PytorchZoo GAN.'
)
parser.add_argument(
    '-m', '--model', metavar='MODEL_NAME',
    default=MODEL_NAME,
    help='Model to use ("anime" or "celeb". Default is "anime").'
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
         'to measure execution performance.'
)
OUTPUT_SIZE = 0 # uninitialized
args = parser.parse_args()
if args.model == 'anime':
    print('Generation using model "AnimeFace"')
    MODEL_INFIX = 'animeface'
    OUTPUT_SIZE = 64
elif args.model == 'celeb':
    print('Generation using model "CelebA"')
    MODEL_INFIX = 'celeba'
    OUTPUT_SIZE = 128
else:
    print('Error: unknown model name "'+args.model+'" (must be "anime" or "celeb")')
    exit(-1)
MODEL_PATH = 'pytorch-gnet-'+MODEL_INFIX+'.onnx.prototxt'
WEIGHT_PATH = 'pytorch-gnet-'+MODEL_INFIX+'.onnx'

def generate_image():
    # prepare input data
    rand_input = np.random.rand(1,512).astype(np.float32)

    # net initialize
    env_id = ailia.get_gpu_environment_id()
    print(f'env_id: {env_id}')
    gnet = ailia.Net(
        MODEL_PATH, WEIGHT_PATH, env_id=env_id
    )

    # inference
    print('Start inference...')
    if args.benchmark:
        print('BENCHMARK mode')
        for i in range(5):
            start = int(round(time.time() * 1000))
            _ = gnet.predict(rand_input)
            end = int(round(time.time() * 1000))
            print(f'\tailia processing time {end - start} ms')
    else:
        _ = gnet.predict(rand_input)
        
    # postprocessing

    [output_blob_idx] = gnet.get_output_blob_list()
    output_data = gnet.get_blob_data(output_blob_idx)

    outp = np.clip((0.5 + 255*output_data.transpose((2,3,1,0)).reshape((OUTPUT_SIZE,OUTPUT_SIZE,3))).astype(np.float32),0,255)

    ## If using PIL instead of OpenCV:
    #from PIL import Image
    #img = Image.fromarray(outp.astype(np.uint8),'RGB')
    #img.save(args.savepath)

    cv2.imwrite(args.savepath, cv2.cvtColor(outp.astype(np.uint8), cv2.COLOR_RGB2BGR))
    print('Script finished successfully.')


def main():
    # model files check and download
    check_and_download_models(WEIGHT_PATH, MODEL_PATH, REMOTE_PATH)

    generate_image()


if __name__ == '__main__':
    main()
