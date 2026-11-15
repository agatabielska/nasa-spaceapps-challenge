"""Conservative closing and component filtering in physical units."""
import numpy as np
from scipy import ndimage
from nisar.detection import clean


def disk(radius):
    y,x=np.ogrid[-radius:radius+1,-radius:radius+1]
    return x*x+y*y<=radius*radius


def close_valid(mask,valid,radius,allowed=None):
    """Fill short gaps, preserve originals and prohibit additions near nodata.

    A closing depends on pixels up to 2r away. Only add where that complete
    neighborhood is valid; do not connect through a missing-data corridor.
    """
    original=np.asarray(mask,dtype=bool)&valid
    if radius<=0:return original.copy()
    footprint=disk(radius)
    candidate=ndimage.binary_closing(original,structure=footprint)
    safe=ndimage.binary_erosion(valid,structure=disk(2*radius),border_value=1)
    added=candidate&safe&valid
    if allowed is not None:added &= allowed
    return original|added


def spatial_fcm_candidates(membership,valid,minimum,margin,radius,fraction):
    other=np.maximum(membership[:,:,0],membership[:,:,1])
    confident=(membership[:,:,2]>=minimum)&((membership[:,:,2]-other)>=margin)&valid
    footprint=disk(radius).astype(np.float32)
    neighbors=ndimage.convolve(confident.astype(np.float32),footprint,mode='constant')
    count=ndimage.convolve(valid.astype(np.float32),footprint,mode='constant')
    agreement=neighbors/np.maximum(count,1)
    return confident,confident&(agreement>=fraction),agreement


def final_cleanup(mask,valid,config,pixel_area,allowed=None):
    radius=int(np.ceil(config.get('physical_closing_radius_m',0)/np.sqrt(pixel_area)))
    closed=close_valid(mask,valid,radius,allowed)
    minimum=max(1,int(np.ceil(config['morphology_min_area_m2']/pixel_area)))
    result=clean(closed,valid,minimum,config.get('morphology_connectivity',4))
    return result,closed,dict(radius_pixels=radius,min_pixels=minimum,
                             added_pixels=int((closed&~mask).sum()),removed_pixels=int((closed&~result).sum()))
