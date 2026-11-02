#include "config.h"
#include "TextureMapper.h"
#include "TextureMapperFlags.h"

extern "C" WEBCORE_EXPORT void rv_native_texture_draw(WebCore::TextureMapper* mapper, unsigned texture,
    const WebCore::FloatRect* target, const WebCore::TransformationMatrix* matrix, float opacity)
{
    mapper->drawTexture(texture, WebCore::TextureMapperFlags::ShouldBlend, *target, *matrix, opacity);
}
