// --- FILE: frontend/src/components/chessboard/BoardTextureLayer.tsx ---
// Procedural board texture layer (task 18.1) over the frame or square colour. The texture is defined in the board theme
// (config/boardAppearance.ts, textureLayerStyle): a file from /assets/textures, opacity and blend mode. For a theme
// without a texture (or with a texture only for dark squares, on a light square) the layer is not created.

import {textureLayerStyle} from '../../config/boardAppearance';
import type {BoardTheme} from '../../config/boardAppearance';

export function BoardTextureLayer({theme, where, isDark = false}: { theme: BoardTheme; where: 'frame' | 'square'; isDark?: boolean }) {
    const style = textureLayerStyle(theme, where, isDark);
    return style ? <div aria-hidden="true" data-testid={`texture-${where}`} className="absolute inset-0 pointer-events-none" style={style}/> : null;
}
