-- 3ds Max 2025 requires MacroScript actions and the #cuiRegisterMenus callback.
-- All maintained BlendMax behavior is implemented in Python.

function blendMaxGetOrCreateMenu menuMgr =
(
    local menuId = "5A6F2E95-18D8-46A1-9A6F-2C0B77C9A2D1"
    local menuItem = menuMgr.getMenuItemById menuId
    if menuItem == undefined then
    (
        local helpMenuId = "CEE8F758-2199-411B-81E7-D3FF4A80D143"
        menuItem = menuMgr.mainMenuBar.CreateSubMenu menuId "BlendMax" beforeId:helpMenuId
    )
    else
    (
        menuItem = menuItem.subMenu
    )
    return menuItem
)

function blendMaxMenuCallback =
(
    local menuMgr = callbacks.notificationParam()
    local blendMaxMenu = blendMaxGetOrCreateMenu menuMgr
    local macroActionTableId = 647394

    blendMaxMenu.CreateAction "A30DAAC2-6717-4BCB-8D7D-0D9F7D47E504" macroActionTableId "BlendMaxExport`BlendMax"
    blendMaxMenu.CreateSeparator "54692125-BF6E-4531-9608-558636FAD8CE"
    blendMaxMenu.CreateAction "9377805D-B6A6-42E9-89DF-E58BC0A62475" macroActionTableId "BlendMaxUpdate`BlendMax"
    blendMaxMenu.CreateAction "C9C2DBCA-67D3-4A5D-BD50-6A80E7167E69" macroActionTableId "BlendMaxProjectPage`BlendMax"
    blendMaxMenu.CreateAction "4EB76424-2942-4E6B-96CA-0D9DE9AD08BE" macroActionTableId "BlendMaxAbout`BlendMax"
)

callbacks.removeScripts id:#blendMaxMenu
callbacks.addScript #cuiRegisterMenus blendMaxMenuCallback id:#blendMaxMenu
