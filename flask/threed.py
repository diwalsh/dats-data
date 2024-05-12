import os
import numpy as np
from skimage import measure
from skimage.morphology import ball
from PIL import Image
from scipy.ndimage import zoom, binary_closing


# load images from a specified 'overlaid' folder (passed as argument)
def load_images_from_folder(folder, prefix):
    images = []
    if not os.path.exists(folder):
        print("The specified folder does not exist.")
        return images
    # Split prefix into parts
    prefix_parts = prefix.split('_')
    for filename in sorted(os.listdir(folder)):
        if filename.startswith(f'{prefix_parts[0]}_{prefix_parts[1]}') and filename.endswith(f'{prefix_parts[2]}_mask.png'):
            img_path = os.path.join(folder, filename)
            try:
                with Image.open(img_path) as img:
                    images.append(np.array(img))
            except IOError:
                print(f"Failed to load {filename}.")
    return images

    
# step 1: extract the color channels into 3D volumes
def extract_organ_masks(images, organ_colors):
    # Initialize a list of volumes for each organ color
    organ_volumes = [np.zeros((images[0].shape[0], images[0].shape[1]), dtype=bool) for _ in organ_colors]
    
    for img in images:
        for idx, color in enumerate(organ_colors):
            # Create a mask where the image matches the specific organ color
            mask = np.all(img == np.array(color, dtype=img.dtype), axis=-1)
            # Stack the mask to build a 3D volume for each organ
            organ_volumes[idx] = np.dstack((organ_volumes[idx], mask))
    
    return organ_volumes


# step 2: interpolate 3D volumes from masks
def interpolate_volumes(volumes, scale_factor):
    return [zoom(volume, (1, 1, scale_factor), order=3) for volume in volumes]


# step 3: apply morphological closing to 3D volumes from masks
def close_volumes(volumes, size=2):
    structure = ball(size)
    return [binary_closing(volume, structure=structure) for volume in volumes]


# step 4: extract mesh from 3D volumes from masks
def extract_mesh_from_volumes(volumes):
    vertices_list = []
    faces_list = []
    colors_list = []  # Initialize colors list
    colors = [[.976, 0.733, 0.749],   # light pink
              [1.0, 0.50, 0.64],     # medium pink
              [0.72, 0.32, 0.40]]     # dark pink
    color_index = 0  

    # Calculate overall center of all organs combined
    overall_center = np.zeros(3, dtype=np.float64)
    total_verts_count = 0

    for volume in volumes:
        threshold = np.max(volume) * 0.5
        volume = volume[:, :, ::-1]  # Adjust coordinate system if necessary
        verts, _, _, _ = measure.marching_cubes(volume, threshold)
        total_verts_count += len(verts)
        overall_center += np.sum(verts, axis=0)

    overall_center /= total_verts_count  # Compute the average to get the center

    # extract mesh for each organ and translate them relative to the overall center
    for i, volume in enumerate(volumes):
        threshold = np.max(volume) * 0.5
        volume = volume[:, :, ::-1]  # Adjust coordinate system if necessary
        verts, faces, _, _ = measure.marching_cubes(volume, threshold)

        # translate vertices relative to the overall center
        verts -= overall_center

        # append vertices, faces and color to their lists
        vertices_list.append(verts)
        faces_list.append(faces)
        colors_list.append([colors[i]] * len(verts))  # Assign color to vertices of the organ
        color_index += 1 # iterate over color index
        
    return vertices_list, faces_list, colors_list


# determine if generated mesh is valid (inside of step 5)
def is_valid_mesh(vertices, faces):
    if len(vertices) == 0 or len(faces) == 0:
        return False
    for face in faces:
        if len(face) != 3:
            return False
        for idx in face:
            if idx < 0 or idx >= len(vertices):
                return False
    return True

# step 5: save to .obj and .mtl files
def save_as_obj_with_mtl(filename, organ_vertices_list, organ_faces_list, organ_colors_list):
    # retrieve base-filename and append extension
    obj_filename = filename
    mtl_filename = filename[:-4] + '.mtl'

    # write .obj file
    with open(obj_filename, 'w') as f:
        vertex_offset = 1  # Start indexing vertices from 1
        for organ_idx, (vertices, faces) in enumerate(zip(organ_vertices_list, organ_faces_list), start=1):
            if not is_valid_mesh(vertices, faces):
                print(f"Invalid mesh data for Organ{organ_idx}. Skipping save.")
                continue
            f.write(f'g Organ{organ_idx}\n')
            for v in vertices:
                f.write(f'v {v[0]} {v[2]} {v[1]}\n')  # Swap y and z coordinates
            f.write(f'mtllib {os.path.basename(mtl_filename)}\n')
            f.write(f'usemtl Organ{organ_idx}\n')
            adjusted_faces = [[idx + vertex_offset for idx in face[::-1]] for face in faces]  # Swap indices for y and z
            for face in adjusted_faces:
                if len(face) != 3:
                    print(f"Skipping invalid face with {len(face)} vertices.")
                    continue
                f.write(f'f {" ".join(map(str, face))}\n')
            vertex_offset += len(vertices)
            
    # write .mtl file
    with open(mtl_filename, 'w') as f:
        for organ_idx, colors in enumerate(organ_colors_list, start=1):
            f.write(f'newmtl Organ{organ_idx}\n')
            f.write(f'Ka {colors[0][0]} {colors[0][1]} {colors[0][2]}\n')  # Ambient color
            f.write(f'Kd {colors[1][0]} {colors[1][1]} {colors[1][2]}\n')  # Diffuse color
            f.write(f'Ks {colors[2][0]} {colors[2][1]} {colors[2][2]}\n')  # Specular color
            f.write(f'Ns 200\n')  # Higher specular exponent for increased reflectivity
            f.write(f'illum 2\n')  # Illumination model
            f.write(f'Ni 1.0\n')  # Optical density (index of refraction)
            f.write(f'd 1.0\n')    # Dissolve factor (opacity)
        

# finally: call above functions in correct order
def threed_render(images, combined_filename, organ_colors):
    # Check if images exist
    if images:
        organ_volumes = extract_organ_masks(images, organ_colors)
        organ_volumes = interpolate_volumes(organ_volumes, scale_factor=2)
        organ_volumes = close_volumes(organ_volumes, size=2)
        
        vertices_list, faces_list, colors_list = extract_mesh_from_volumes(organ_volumes)
        save_as_obj_with_mtl(combined_filename, vertices_list, faces_list, colors_list)
        print(f"All organs saved as {combined_filename}")
    else:
        print("No images to process.")
        
        