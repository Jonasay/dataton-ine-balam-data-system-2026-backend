import argparse
import math
import os
import sys

import bpy
import mathutils


# paleta de colores de los 22 departamentos en espacio lineal para blender
DEPT_COLORS_BLENDER = {
    "01": (0.05, 0.22, 0.90),  # guatemala: azul real
    "02": (0.01, 0.50, 0.13),  # el progreso: esmeralda
    "03": (0.90, 0.35, 0.01),  # sacatepequez: ambar
    "04": (0.85, 0.07, 0.07),  # chimaltenango: rojo coral
    "05": (0.26, 0.12, 0.88),  # escuintla: purpura
    "06": (0.83, 0.08, 0.33),  # santa rosa: rosa intenso
    "07": (0.01, 0.38, 0.79),  # solola: celeste lago
    "08": (0.94, 0.18, 0.01),  # totonicapan: naranja
    "09": (0.40, 0.10, 0.86),  # quetzaltenango: violeta
    "10": (0.02, 0.56, 0.11),  # suchitepequez: verde
    "11": (0.82, 0.49, 0.01),  # retalhuleu: amarillo dorado
    "12": (0.01, 0.47, 0.65),  # san marcos: turquesa
    "13": (0.75, 0.01, 0.07),  # huehuetenango: carmin
    "14": (0.69, 0.07, 0.86),  # quiche: fucsia
    "15": (0.01, 0.48, 0.39),  # baja verapaz: teal
    "16": (0.24, 0.60, 0.01),  # alta verapaz: lima
    "17": (0.09, 0.07, 0.80),  # peten: indigo
    "18": (0.01, 0.24, 0.77),  # izabal: azul caribe
    "19": (0.54, 0.06, 0.01),  # zacapa: ocre
    "20": (0.47, 0.10, 0.01),  # chiquimula: bronce
    "21": (0.34, 0.01, 0.08),  # jalapa: magenta
    "22": (0.13, 0.37, 0.01),  # jutiapa: oliva
}


def parse_args():
    # extraer argumentos pasados despues del delimitador --
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Renderizar modelo 3D de Guatemala con Blender")
    parser.add_argument("--input", required=True, help="Ruta del archivo GLB o STL de entrada")
    parser.add_argument("--output", required=True, help="Ruta de la imagen PNG resultante")
    parser.add_argument("--width", type=int, default=1280, help="Ancho de renderizado en pixeles")
    parser.add_argument("--height", type=int, default=720, help="Alto de renderizado en pixeles")
    parser.add_argument("--samples", type=int, default=32, help="Muestras de renderizado")
    parser.add_argument("--color-mode", default="multicolor", choices=["multicolor", "black", "blue"], help="Modo de color de los relieves")
    return parser.parse_args(argv)


def setup_scene(input_file, output_file, width, height, samples, color_mode="multicolor"):
    # limpiar escena por defecto
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # importar modelo segun extension
    ext = os.path.splitext(input_file)[-1].lower()
    if ext in [".glb", ".gltf"]:
        bpy.ops.import_scene.gltf(filepath=input_file)
    elif ext == ".stl":
        if hasattr(bpy.ops.wm, "stl_import"):
            bpy.ops.wm.stl_import(filepath=input_file)
        else:
            bpy.ops.import_mesh.stl(filepath=input_file)
    else:
        raise ValueError(f"Formato no soportado: {ext}")

    # recolectar geometrias importadas
    mesh_objs = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not mesh_objs:
        raise RuntimeError("No se encontraron mallas en el archivo importado")

    # calcular caja envolvente para centrar la camara
    all_coords = []
    for obj in mesh_objs:
        for v in obj.data.vertices:
            all_coords.append(obj.matrix_world @ v.co)

    if all_coords:
        min_x = min(c.x for c in all_coords)
        max_x = max(c.x for c in all_coords)
        min_y = min(c.y for c in all_coords)
        max_y = max(c.y for c in all_coords)
        min_z = min(c.z for c in all_coords)
        max_z = max(c.z for c in all_coords)
    else:
        min_x, max_x = -75, 75
        min_y, max_y = -75, 75
        min_z, max_z = 0, 50

    center = mathutils.Vector(((min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2))
    size = max(max_x - min_x, max_y - min_y, max_z - min_z, 100.0)

    # aplicar materiales segun color_mode seleccionado
    if color_mode == "black":
        # modo relieve negro mate con contraste escultorico
        black_mat = bpy.data.materials.new(name="RelieveNegroMat")
        black_mat.use_nodes = True
        bsdf = black_mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.03, 0.03, 0.04, 1.0)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = 0.28
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = 0.40
        for obj in mesh_objs:
            if "base" in obj.name.lower():
                continue
            if obj.data.materials:
                obj.data.materials[0] = black_mat
            else:
                obj.data.materials.append(black_mat)
    elif color_mode == "multicolor":
        # asignar color especifico para cada departamento
        for idx, obj in enumerate(mesh_objs):
            if "base" in obj.name.lower():
                continue
            code = ""
            for token in obj.name.split("_"):
                if token.isdigit() and len(token) <= 2:
                    code = token.zfill(2)
                    break
            if not code:
                code = f"{(idx % 22) + 1:02d}"
            c_rgb = DEPT_COLORS_BLENDER.get(code, (0.05, 0.35, 0.75))
            d_mat = bpy.data.materials.new(name=f"Mat_{obj.name}")
            d_mat.use_nodes = True
            b_bsdf = d_mat.node_tree.nodes.get("Principled BSDF")
            if b_bsdf:
                b_bsdf.inputs["Base Color"].default_value = (*c_rgb, 1.0)
                if "Roughness" in b_bsdf.inputs:
                    b_bsdf.inputs["Roughness"].default_value = 0.32
                if "Metallic" in b_bsdf.inputs:
                    b_bsdf.inputs["Metallic"].default_value = 0.15
            if obj.data.materials:
                obj.data.materials[0] = d_mat
            else:
                obj.data.materials.append(d_mat)
    else:
        # azul petroleo clasico
        blue_mat = bpy.data.materials.new(name="RelieveAzulMat")
        blue_mat.use_nodes = True
        b_bsdf = blue_mat.node_tree.nodes.get("Principled BSDF")
        if b_bsdf:
            b_bsdf.inputs["Base Color"].default_value = (0.05, 0.28, 0.45, 1.0)
            if "Roughness" in b_bsdf.inputs:
                b_bsdf.inputs["Roughness"].default_value = 0.35
            if "Metallic" in b_bsdf.inputs:
                b_bsdf.inputs["Metallic"].default_value = 0.25
        for obj in mesh_objs:
            if "base" in obj.name.lower():
                continue
            if obj.data.materials:
                obj.data.materials[0] = blue_mat
            else:
                obj.data.materials.append(blue_mat)

    # material para placa base
    base_mat = bpy.data.materials.new(name="BaseSoporteMat")
    base_mat.use_nodes = True
    f_bsdf = base_mat.node_tree.nodes.get("Principled BSDF")
    if f_bsdf:
        f_bsdf.inputs["Base Color"].default_value = (0.02, 0.03, 0.05, 1.0)
        if "Roughness" in f_bsdf.inputs:
            f_bsdf.inputs["Roughness"].default_value = 0.6
    for obj in mesh_objs:
        if "base" in obj.name.lower():
            if obj.data.materials:
                obj.data.materials[0] = base_mat
            else:
                obj.data.materials.append(base_mat)

    # agregar plano de piso tipo estudio fotografico
    bpy.ops.mesh.primitive_plane_add(size=size * 8, location=(center.x, center.y, min_z - 0.5))
    floor = bpy.context.active_object
    floor_mat = bpy.data.materials.new(name="FloorMat")
    floor_mat.use_nodes = True
    f_bsdf = floor_mat.node_tree.nodes.get("Principled BSDF")
    if f_bsdf:
        f_bsdf.inputs["Base Color"].default_value = (0.04, 0.06, 0.10, 1.0)
        if "Roughness" in f_bsdf.inputs:
            f_bsdf.inputs["Roughness"].default_value = 0.8
    floor.data.materials.append(floor_mat)

    # configurar camara en angulo isometrico
    cam_data = bpy.data.cameras.new("MainCam")
    cam_data.lens = 50
    cam_obj = bpy.data.objects.new("MainCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    cam_dist = size * 1.8
    cam_obj.location = (
        center.x + cam_dist * 0.7,
        center.y - cam_dist * 0.9,
        center.z + cam_dist * 0.85
    )
    direction = center - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    # iluminacion de estudio en 3 puntos
    # 1. key light (luz principal calida)
    key_data = bpy.data.lights.new(name="KeyLight", type="SUN")
    key_data.energy = 4.5
    key_data.color = (1.0, 0.95, 0.88)
    key_obj = bpy.data.objects.new(name="KeyLight", object_data=key_data)
    bpy.context.scene.collection.objects.link(key_obj)
    key_obj.location = (center.x + size, center.y - size, center.z + size * 1.5)
    key_obj.rotation_euler = (math.radians(45), math.radians(15), math.radians(35))

    # 2. fill light (luz de relleno azulada suave)
    fill_data = bpy.data.lights.new(name="FillLight", type="SUN")
    fill_data.energy = 2.0
    fill_data.color = (0.6, 0.8, 1.0)
    fill_obj = bpy.data.objects.new(name="FillLight", object_data=fill_data)
    bpy.context.scene.collection.objects.link(fill_obj)
    fill_obj.location = (center.x - size, center.y - size, center.z + size)
    fill_obj.rotation_euler = (math.radians(50), math.radians(-20), math.radians(-45))

    # 3. rim light (contraluz para recortar el relieve)
    rim_data = bpy.data.lights.new(name="RimLight", type="SUN")
    rim_data.energy = 3.0
    rim_data.color = (0.4, 0.9, 1.0)
    rim_obj = bpy.data.objects.new(name="RimLight", object_data=rim_data)
    bpy.context.scene.collection.objects.link(rim_obj)
    rim_obj.location = (center.x, center.y + size * 1.5, center.z + size)
    rim_obj.rotation_euler = (math.radians(-60), 0, math.radians(180))

    # configurar resolucion y motor de renderizado
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.filepath = output_file
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    # renderizar escena
    print(f"Renderizando a {output_file} ({width}x{height})...")
    bpy.ops.render.render(write_still=True)
    print("Renderizado completado exitosamente.")


if __name__ == "__main__":
    args = parse_args()
    setup_scene(
        input_file=args.input,
        output_file=args.output,
        width=args.width,
        height=args.height,
        samples=args.samples,
        color_mode=args.color_mode
    )
