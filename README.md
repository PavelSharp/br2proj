# Welcome to br2proj

## Intro

br2proj is a new, modern, and open-source utility for processing Bloodrayne 2 game files.

This is implemented as an addon for [Blender](https://www.blender.org). Tested only on Blender 4.3.

Currently, it supports importing the following file formats:

1. **TEX** – Uncompressed raster images.
2. **SMB** – A format designed for storing 3D models. It turned out to be more complex than expected, as it includes animations and model variations at different levels of damage.
3. **BFM(with SKB)** – A mainstream 3D data format that uses skeletal structures and skeletal animation. It also supports gap meshes-special meshes that cover joints when a character is dismembered.

From now on, you can import these files directly into Blender!

And of course, feel free to open an issue. This is the place where you can share ideas for improvement as well as report any problems you encounter.

## How to install?
Open blender go to the `Scripting` tab, and just paste the contents of [build.py](https://github.com/PavelSharp/br2proj/blob/main/build.py), then click on the run button. Done.

This is a fairly clever script that will download and install the latest version itself automatically. 

You may need to enable “Allow Online Access” in `Edit`→`Preferences`→`System`, although my tests don't confirm this.  

If any exceptions have been generated, going to `Windows`→`Toggle System Console` should give detailed information on the progress of the execution

## How is it developed?
Visual Studio Code with [Blender Development](https://marketplace.visualstudio.com/items?itemName=JacquesLucke.blender-development)

## History
Almost 20 years ago, PodTools was a popular tool, but unfortunately, its development stopped in 2006. Support for animations (.ani files) was never completed, and the source code remained closed.

PodTools worked alongside BR_Tools (by BloodHammer) within gmax to enable exporting. For years, BR_Tools was considered lost-until KillerExe_01 published it [here](http://gamebanana.com/tools/18509).

Excited, I downloaded the archive, only to be disappointed once again - BR_Tools was also closed-source. However, the archive contained something valuable: the "BR2 3D FILE FORMATS DOCUMENT by BloodHammer(Mjolnir) (v1.19 - 15.01.2006)", which detailed past efforts to reverse-engineer the game's formats.

That was back in October 2024. At the time, I didn’t have the bandwidth to dive in, but starting in February 2025, I finally dedicated myself to building everything from scratch.

Now, I’m thrilled to share my progress with you!

## TODO
1. Animation import support (stored in .ani)
2. Export of these formats as far-reaching plans
3. Basic support for bloodrayne 1 as very far-reaching plans