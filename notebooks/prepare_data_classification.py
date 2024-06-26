# Import required libraries
import os
import re
import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm
from sklearn.model_selection import train_test_split
 
TEST_PAT = "['2', '6', '7', '9', '11', '15', '16', '140', '145', '146', '147', '148', '149', '154', '156']"

# Define regular expressions to extract case, date, slice number, and image shape from file paths
GET_CASE = re.compile(r"case[0-9]{1-3}")
GET_CASE_AND_DATE = re.compile(r"case[0-9]{1,3}_day[0-9]{1,3}")
GET_SLICE_NUM = re.compile(r"slice_[0-9]{1,4}")
IMG_SHAPE = re.compile(r"_[0-9]{1,3}_[0-9]{1,3}_")
 
# Define classes for image segmentation
CLASSES = ["large_bowel", "small_bowel", "stomach"]
  
# Function to get all relevant image files in a given directory
def get_folder_files(folder_path, only_IDS):
    all_relevant_imgs_in_case = []
    img_ids = []

    # images\train\case11\case11_day0\scans ['slice_0001_360_310_1.50_1.50.png', 'slice_0002_360_310_1.50_1.50.png',  
    #'slice_0003_360_310_1.50_1.50.png', 'slice_0004_360_310_1.50_1.50.png',...]
    for dir, _, files in os.walk(folder_path):
        if not len(files):
            continue
        # goes over the list of image names
        for file_name in files:
            src_file_path = os.path.join(dir, file_name)

            # creates the file_name of the preprocessed images
            case_day = GET_CASE_AND_DATE.search(src_file_path).group()
            slice_id = GET_SLICE_NUM.search(src_file_path).group()
            image_id = case_day + "_" + slice_id

            # checks if the image_id is present in the only_IDS list
            if image_id in only_IDS:
                all_relevant_imgs_in_case.append(src_file_path)
                img_ids.append(image_id)
                
    # It returns the lists all_relevant_imgs_in_case (containing paths to relevant image files) and img_ids (containing corresponding image IDs).
    return all_relevant_imgs_in_case, img_ids
 
# Function to get all relevant image files in a given directory
def get_folder_files_2p5d(folder_path, only_IDS, stride=1):
    all_relevant_imgs_in_case = []
    img_ids = []

    # images\train\case11\case11_day0\scans ['slice_0001_360_310_1.50_1.50.png', 'slice_0002_360_310_1.50_1.50.png',  
    #'slice_0003_360_310_1.50_1.50.png', 'slice_0004_360_310_1.50_1.50.png',...]
    for dir, _, files in os.walk(folder_path):
        if not len(files):
            continue
        # goes over the list of image names and creates 2.5d image
        L = len(files)
        for idx, _ in enumerate(files):            
            src_file_path = os.path.join(dir, files[idx])
            src_file_path_p1 = os.path.join(dir, files[min(idx + 1*stride, L-1)])
            src_file_path_p2 = os.path.join(dir, files[min(idx + 2*stride, L-1)])
            src_file_paths = [src_file_path, src_file_path_p1, src_file_path_p2]
            
            # creates the file_name of the preprocessed images
            case_day = GET_CASE_AND_DATE.search(src_file_path).group()
            slice_id = GET_SLICE_NUM.search(src_file_path).group()
            image_id = case_day + "_" + slice_id

            # checks if the image_id is present in the only_IDS list
            if image_id in only_IDS:
                all_relevant_imgs_in_case.append(src_file_paths)
                img_ids.append(image_id)
                
    # It returns the lists all_relevant_imgs_in_case (containing paths to relevant image files) and img_ids (containing corresponding image IDs).
    return all_relevant_imgs_in_case, img_ids

# Function to decode Run-Length Encoding (RLE) into an image mask
# ref: https://www.kaggle.com/paulorzp/run-length-encode-and-decode
def rle_decode(mask_rle, shape):
    """
    mask_rle: run-length as string formated (start length)
    shape: (height,width) of array to return
    Returns numpy array, 1 - mask, 0 - background
 
    """
    s = np.asarray(mask_rle.split(), dtype=int)
    starts = s[0::2] - 1
    lengths = s[1::2]
    ends = starts + lengths
    img = np.zeros(shape[0] * shape[1], dtype=np.uint8)
    for lo, hi in zip(starts, ends):
        img[lo:hi] = 1
    return img.reshape(shape)  # Needed to align to RLE direction
 
 
# Function to load and convert image from a uint16 to uint8 datatype.
def load_img(img_path):
    # reads the image file specified in img_path.
    # cv2.IMREAD_UNCHANGED indicates that the image is loades as-is
    # The result is stored in img and then coverted to float32.
    img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED).astype(np.float32)
    # pefroms mix-max normalization on the image array.
    # this normalization ensure that the pixel values are withing the range of 8-bit grayscale or RGB mages
    img = (img - img.min()) / (img.max() - img.min()) * 255.0
    # conversion to unit8 (8-bits)
    img = img.astype(np.uint8)
    # checks if the image is grayscale and, if so, converts it to an RGB image by replicating the single-channel
    # (grayscale) image to three channels (R, G, B) using np.tile()
    img = np.tile(img[..., None], [1, 1, 3])  # gray to rgb
  
    return img

# Function to load three adjacent images and store them in an RGB image format
# img_paths is a list of image paths: [path/img_i-1.png, path/img_i.png, path/img_i+1.png]
def load_img_2p5d(img_paths):
    no_images = len(img_paths)
    img_shape = list(map(int, IMG_SHAPE.search(img_paths[0]).group()[1:-1].split("_")))[::-1]
    img_shape.append(no_images)
    img = np.zeros(tuple(img_shape))
    for idx, img_path in enumerate(img_paths):
        # reads the image file specified in img_path.
        ch = cv2.imread(img_path, cv2.IMREAD_UNCHANGED).astype(np.float32)
        # performs mix-max normalization on the image array.
        ch = (ch - ch.min()) / (ch.max() - ch.min()) * 255.0
        # conversion to unit8 (8-bits)
        ch = ch.astype(np.uint8)
        img[:,:,idx] = ch
        if idx == 2:
            break
    
    return img
         
# Function to create and write images for each file path in given directories.
def create_and_write_img(file_paths, file_ids, save_dir_0, save_dir_1, main_df, desc=None):
    # iterates over each file_path and file_id pair using zip(file_paths, file_ids), while also displaying a progress bar using tqdm.
    for file_path, file_id in tqdm(zip(file_paths, file_ids), ascii=True, total=len(file_ids), desc=desc, leave=True):
        # loads the image corresponding to the current file_path using the load_img function.
        image = load_img(file_path)

        # retrieves the rows from the DataFrame MAIN_DF where the "id" column matches the current file_id.
        IMG_DF = main_df[main_df["id"] == file_id]
        # detects if the image contains the organs of interest (stomach, small bowel, larg bowel)
        all_zeros = (IMG_DF["classification"] == 0).all()
        
        # extracts the case and date information from the file path and the file name.
        FILE_CASE_AND_DATE = GET_CASE_AND_DATE.search(file_path).group()
        FILE_SLICE_NUMBER = GET_SLICE_NUM.search(file_path).group()
        
        # splits the file_path into two parts: the directory path and the file name. It returns these two parts as a tuple (directory_path, file_name)
        FILE_NAME = os.path.split(file_path)[-1]

        # constructs new file names for the image and mask files based on the case, date, and original file name.
        # It then creates the destination paths for saving the image and mask files.
        new_name = FILE_CASE_AND_DATE + "_" + FILE_SLICE_NUMBER + ".png"      
        #FILE_NAME

        if all_zeros:
            dst_img_path = os.path.join(save_dir_0, new_name)
        else:
            dst_img_path = os.path.join(save_dir_1, new_name)
            
        # writes the image and mask arrays to the corresponding destination paths using cv2.imwrite.
        cv2.imwrite(dst_img_path, image)
        
    return

# Function to create and write images for each file path in given directories.
def create_and_write_img_2p5d(file_paths, file_ids, save_dir_0, save_dir_1, main_df, desc=None):
    # iterates over each file_path and file_id pair using zip(file_paths, file_ids), while also displaying a progress bar using tqdm.
    for file_path, file_id in tqdm(zip(file_paths, file_ids), ascii=True, total=len(file_ids), desc=desc, leave=True):
        # loads the image corresponding to the current file_path using the load_img function.
        image = load_img_2p5d(file_path)

        # retrieves the rows from the DataFrame MAIN_DF where the "id" column matches the current file_id.
        IMG_DF = main_df[main_df["id"] == file_id]
        # detects if the image contains the organs of interest (stomach, small bowel, larg bowel)
        all_zeros = (IMG_DF["classification"] == 0).all()
        
        # extracts the case and date information from the file path and the file name.
        FILE_CASE_AND_DATE = GET_CASE_AND_DATE.search(file_path[0]).group()
        FILE_SLICE_NUMBER = GET_SLICE_NUM.search(file_path[0]).group()
        
        # splits the file_path into two parts: the directory path and the file name. It returns these two parts as a tuple (directory_path, file_name)
        FILE_NAME = os.path.split(file_path[0])[-1]

        # constructs new file names for the image and mask files based on the case, date, and original file name.
        # It then creates the destination paths for saving the image and mask files.
        #new_name = FILE_CASE_AND_DATE + "_" + FILE_SLICE_NUMBER + ".png"
        new_name = FILE_CASE_AND_DATE + "_" + FILE_NAME
        #FILE_NAME

        if all_zeros:
            dst_img_path = os.path.join(save_dir_0, new_name)
        else:
            dst_img_path = os.path.join(save_dir_1, new_name)
            
        # writes the image and mask arrays to the corresponding destination paths using cv2.imwrite.
        cv2.imwrite(dst_img_path, image)
        
    return

import argparse

def main(dimension, stride, csv, input_dir, output_dir, test_patients):
    
    # Process input parameters
    print("Dimension:", dimension)
    print("Stride:", stride)
    print("CSV:", csv)
    print("Input Dir:", input_dir)
    print("Output Dir:", output_dir)
    print("Test Patients:", test_patients)
    
    # Set random seed for reproducibility
    np.random.seed(42)

    # Define paths for training dataset and image directory
    TRAIN_CSV = csv

    ORIG_IMG_DIR = input_dir #os.path.join(input_dir,train)
    CASE_FOLDERS = os.listdir(ORIG_IMG_DIR)

    # Define paths for training and test image and mask directories
    ROOT_DATASET_DIR = output_dir
    ROOT_TRAIN_DIR_0 = os.path.join(ROOT_DATASET_DIR, "train", "0")
    ROOT_TRAIN_DIR_1 = os.path.join(ROOT_DATASET_DIR, "train", "1")
    ROOT_TEST_DIR_0 = os.path.join(ROOT_DATASET_DIR, "test", "0")
    ROOT_TEST_DIR_1 = os.path.join(ROOT_DATASET_DIR, "test", "1")
     
    # Create directories if not already present
    os.makedirs(ROOT_TRAIN_DIR_0, exist_ok=True)
    os.makedirs(ROOT_TRAIN_DIR_1, exist_ok=True)
    os.makedirs(ROOT_TEST_DIR_0, exist_ok=True)
    os.makedirs(ROOT_TEST_DIR_1, exist_ok=True)

    # Load the main dataframe from csv file
    oDF = pd.read_csv(TRAIN_CSV)
    oIDS = oDF["id"].to_numpy()
    mask = (~oDF["segmentation"].isna()).astype(int)
    oDF['classification'] = mask
    
    # Main script execution: for each folder, split the data into training and test sets, and create/write image-mask pairs.
    if dimension != '2.5d':
        if dimension != '2d':
            print("The dimension is different to the specified ones. Using 2d by default")
        for folder in CASE_FOLDERS:
            files, ids = get_folder_files(folder_path=os.path.join(ORIG_IMG_DIR, folder), only_IDS=oIDS)
            if folder[4:] in test_patients:
                create_and_write_img(files, ids, ROOT_TEST_DIR_0, ROOT_TEST_DIR_1, main_df=oDF, desc=f"Test :: {folder}")
            else:
                create_and_write_img(files, ids, ROOT_TRAIN_DIR_0, ROOT_TRAIN_DIR_1, main_df=oDF, desc=f"Train :: {folder}")
    else:
        for folder in CASE_FOLDERS:
            files, ids = get_folder_files_2p5d(folder_path=os.path.join(ORIG_IMG_DIR, folder), only_IDS=oIDS, stride=stride)
            if folder[4:] in test_patients:
                create_and_write_img_2p5d(files, ids, ROOT_TEST_DIR_0, ROOT_TEST_DIR_1, main_df=oDF, desc=f"Test :: {folder}")
            else:
                create_and_write_img_2p5d(files, ids, ROOT_TRAIN_DIR_0, ROOT_TRAIN_DIR_1, main_df=oDF, desc=f"Train :: {folder}")


if __name__ == "__main__":

    import argparse
    import ast

    parser = argparse.ArgumentParser()
    # Define input parameters
    parser.add_argument("-dimension", choices=['2d', '2.5d'], default='2d', help="Choose either '2d' or '2.5d'")
    parser.add_argument("-stride", type=int, default=1, help="Specify the stride as an integer (default 1) for 2.5d")
    parser.add_argument("-csv", type=str, default='data/train.csv', help="Path and file name of the csv file with rle data (default 'data/train.csv)'")
    parser.add_argument("-input_dir", type=str, default='images', help="Specify the directory where the input images reside (default 'images')")
    parser.add_argument("-output_dir", type=str, default='output', help="Specify the directory where the images will be stored (default 'output')")
    parser.add_argument("-test_patients", type=str, default=TEST_PAT, help=f"Specify the list of test images (default \"{TEST_PAT}\")")
    
    args = parser.parse_args()

    # Convert test_patients argument to a list
    args.test_patients = ast.literal_eval(args.test_patients)

    # Check if no arguments are provided, then print help
    #if not any(vars(args).values()):
    if not vars(args):
        parser.print_help()
    else:
        # Call the main function with the parsed arguments
        main(args.dimension, args.stride, args.csv, args.input_dir, args.output_dir, args.test_patients)