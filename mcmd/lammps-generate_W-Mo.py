#!/usr/bin/env python3
"""
Script created by F.Tarulli on 05/21/25.

This script generates four LAMMPS input files:
  1) <sys>.in
  2) <sys>.in.init
  3) <sys>.in.settings
  4) <sys>.in.run

Goal: Create realistic configurations of HEAs via MC-MD approach.

Customize the CONFIGURATION block to adjust elements, fractions, lattice,
replicates, file names, force-field, MD/MC parameters, etc.

ATTENTION:
To run this script on ENI CLUSTER you should firstly lunch "module load tools/python/3.9.1"
"""
import os
import random



# ==================== CONFIGURATION ====================
elements   = ["W", "Mo"]                    # element
ratios     = [1/2, 1/2]    		    # provide them in fraction
replicates = (37, 37, 37)                   # x, y, z replication
lattice_ty = "bcc"                          # lattice type
lattice_a  = 3.165                          # lattice constant [Ang]

temp       = 300.0               # [K]
temp_damp  = 0.1                 # [ps]
press      = 0                   # [bars]
press_damp = 1.0                 # [ps]
timestep   = 0.001               # [ps]
mc_N       = 250                 # [-] invoke atom/swap every mc_N steps
mc_X       = 333                 # [-] number of swaps to attempt every mc_X steps
run_steps  = 500000              # [-] steps for mcmd
N_dump     = 1000                # [-] dump on timesteps which are multiples of N_dump


sysname    = "-".join(elements)
suffixes   = ["ref", "minimized", "mcmd"]
out0, out1, out2 = [f"{sysname}_{s}.data" for s in suffixes]

ffstyle    = "eam/fs"
ffpath     = "/data1/projects/StoRIES/MOL-E/potentials/eam/W-Mo.eam.fs"
# ================= END CONFIGURATION ====================





# Derived names and helpers
n = len(elements)
sysname = "".join(elements)
template_base = "mcmd_" + sysname
seed = random.randint(100000, 999999)
elem_list = ' '.join(elements)
type_list = ' '.join(str(i) for i in range(1, n+1))
rep_str = '${nr} ${nr} ${nr}'
rounded = [round(f, 10) for f in ratios[:-1]] 
last = round(1.0 - sum(rounded), 10) 
fractions = [f"{r:.10f}" for r in rounded] + [f"{last:.10f}"]
fractions_floats = [float(s) for s in fractions]
ratio_block = "\n".join(
    f"    set type 1 type/ratio {i+1} "
    f"    {fractions_floats[i]/(1 - sum(fractions_floats[1:i])):.10f} {12345 + i}"
    for i in range(1, len(fractions_floats))
)

# 1) <template_base>.in
driver_tpl = f"""
# ----------------- Init Section -----------------

include "{template_base}.in.init"

# ----------------- Settings Section -----------------

include "{template_base}.in.settings"

# ----------------- Run Section -----------------

include "{template_base}.in.run"
"""

# 2) Init: <template_base>.in.init
init_tpl = f"""
# Parameters
    variable nr equal {replicates[0]}       # number of box replications per axis
    variable a0 equal {lattice_a}           # lattice constant [Å]
    variable temp equal {temp}              # target temperature [K]
    variable temp_damp equal {temp_damp}    # thermostat damping time [ps]
    variable press equal {press}            # target pressure [bar]
    variable press_damp equal {press_damp}  # barostat damping time [ps]
    variable dt equal {timestep}            # integration timestep [ps]


# Output filenames
    variable out0 string "{out0}"
    variable out1 string "{out1}"
    variable out2 string "{out2}"


# Potential
    variable ff_style string "{ffstyle}"
    variable ff string "{ffpath}"
"""

# 3) Settings: <template_base>.in.settings
settings_tpl = f"""
# Details
    units      metal
    dimension  3
    boundary   p p p
    atom_style atomic
    atom_modify map array


# Lattice generation
    lattice    {lattice_ty} ${{a0}}
    region     box block 0 1 0 1 0 1 units lattice
    create_box {n} box
    create_atoms 1 box
    replicate  {replicates[0]} {replicates[1]} {replicates[2]}

# Atom types by ratio

{ratio_block}


# Potential settings
    pair_style ${{ff_style}}
    pair_coeff * * ${{ff}} {elem_list}
    neighbor 2.0 bin
    neigh_modify delay 0 every 1 check yes


# Atoms collection
    group alloy type {type_list}


# Save data
    write_data ${{out0}}
"""

# 4) Run: <template_base>.in.run
# Generate MC swaps dynamically
mc_swaps = []
for i in range(1, n+1):
    for j in range(i+1, n+1):
        mc_swaps.append(
            f"    fix swap{i}{j} all atom/swap {mc_N} {mc_X} 12345 {temp} ke no types {i} {j}"
        )
mc_block = "\n".join(mc_swaps)

run_tpl = f"""
# Thermo
    variable pea_avg equal "pe/atoms"       # average potential energy per atom [eV]
    variable kea_avg equal "ke/atoms"     # average kinetic energy per atom [eV]
    
    thermo 1000
    thermo_style custom step temp press lx ly lz density pe ke v_pea_avg v_kea_avg cpu


# Minimization
    fix myMin all box/relax iso 0.0 vmax 0.001
    min_style cg
    minimize 1e-4 1e-5 1000 10000
    unfix myMin
    reset_timestep 0
    write_data ${{out1}}


# MDMC
    timestep ${{dt}}
    velocity all create ${{temp}} {seed} rot yes dist gaussian

    dump myDump all custom {N_dump} {sysname}.dump id type x y z xu yu zu vx vy vz
    dump_modify myDump element {elem_list}

    fix myMD all npt temp ${{temp}} ${{temp}} ${{temp_damp}} aniso ${{press}} ${{press}} ${{press_damp}}

    # Monte Carlo swaps
{mc_block}
    run {run_steps}

    # Output saving
    write_data ${{out2}}
    write_restart step{run_steps}_{sysname}.restart
"""

# Write all files
def write_file(name, content):
    with open(name, 'w') as f:
        f.write(content)
    print(f"Wrote {name}")

write_file(f"{template_base}.in", driver_tpl)
write_file(f"{template_base}.in.init", init_tpl)
write_file(f"{template_base}.in.settings", settings_tpl)
write_file(f"{template_base}.in.run", run_tpl)                                                      
