macroScript BlendMaxExport category:"BlendMax" tooltip:"Export a BlendMax asset" buttonText:"Export Asset..."
(
    local scriptDir = getFilenamePath (getSourceFileName())
    local pyFile = scriptDir + "..\\python\\launch_export.py"
    python.ExecuteFile pyFile throwOnError:true
)

macroScript BlendMaxJoinByMaterial category:"BlendMax" tooltip:"Join visible mesh faces by material" buttonText:"Join Mesh by Material..."
(
    local scriptDir = getFilenamePath (getSourceFileName())
    local pyFile = scriptDir + "..\\python\\launch_join_by_material.py"
    python.ExecuteFile pyFile throwOnError:true
)

macroScript BlendMaxUpdate category:"BlendMax" tooltip:"Install a BlendMax update ZIP" buttonText:"Install Update from ZIP..."
(
    local scriptDir = getFilenamePath (getSourceFileName())
    local pyFile = scriptDir + "..\\python\\launch_update.py"
    python.ExecuteFile pyFile throwOnError:true
)

macroScript BlendMaxProjectPage category:"BlendMax" tooltip:"Open the BlendMax GitHub project" buttonText:"Project Page"
(
    local scriptDir = getFilenamePath (getSourceFileName())
    local pyFile = scriptDir + "..\\python\\launch_project_page.py"
    python.ExecuteFile pyFile throwOnError:true
)

macroScript BlendMaxAbout category:"BlendMax" tooltip:"Show BlendMax version information" buttonText:"About BlendMax"
(
    local scriptDir = getFilenamePath (getSourceFileName())
    local pyFile = scriptDir + "..\\python\\launch_about.py"
    python.ExecuteFile pyFile throwOnError:true
)
