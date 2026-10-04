"""Visualize the frozen mapper's native texture sample selection."""
from pathlib import Path
exec((Path(__file__).resolve().parent/'review_rotation.py').read_text().split("report = ")[0])
manual=json.loads((ROOT/'diagnostics/fruit340-fix/20261004_motion/manual_correspondences.json').read_text())['markers']
report=[]
tiles=[]
for frame in (308,309,310,311):
    index=next(i for i,v in enumerate(views) if v.frame_index==frame)
    view=views[index]
    points,_,_=alg._relevant(view,model,index,replace(s,image_downsample=1,highpass_sigma=5.))
    xy=points[:,:2]+model.ellipses[index].center
    marker=np.array(manual[str(frame)]['crop_xy'])
    e=model.ellipses[index]
    delta=marker-e.center
    marker_radius=float(np.sqrt((delta@e.v_major/e.major)**2+(delta@e.v_minor/e.minor)**2))
    distances=np.linalg.norm(xy-marker,axis=1)
    green=np.log(np.maximum(view.image[:,:,1].astype(np.float32)/255.,1/255.))
    patches=alg._surface_patches(points,model.matrices[index],5.)
    _,valid=alg._patch_response(green,patches[None],model.ellipses[index].center,view.object_mask,model.matrices[index])
    row={'frame':frame,'native_point_count':len(xy),'points_within_five_px_of_freckle':int((distances<=5).sum()),'points_within_ten_px_of_freckle':int((distances<=10).sum()),'closest_point_distance_px':float(distances.min()),'valid_patch_fraction':float(valid.mean()),'freckle_normalized_ellipse_radius':marker_radius,'freckle_inside_texture_roi':marker_radius<.66,'native_points':xy.tolist()}
    report.append(row)
    canvas=cv2.resize(view.image,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST)
    for point in xy:
        cv2.circle(canvas,tuple(np.rint(point*3).astype(int)),2,(40,40,255),-1)
    cv2.circle(canvas,tuple(np.rint(marker*3).astype(int)),15,(0,255,255),2)
    cv2.putText(canvas,f'Frame {frame} / {len(xy)} selected samples',(8,24),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),2)
    tile=np.full((max(v.image.shape[0] for v in views)*3,max(v.image.shape[1] for v in views)*3,3),20,np.uint8)
    tile[:canvas.shape[0],:canvas.shape[1]]=canvas
    tiles.append(tile)
cv2.imwrite(str(OUT/'native_selected_points.png'),np.vstack((np.hstack(tiles[:2]),np.hstack(tiles[2:]))))
(OUT/'selected_points_review.json').write_text(json.dumps(report,indent=2))
print([{k:v for k,v in row.items() if k!='native_points'} for row in report])
