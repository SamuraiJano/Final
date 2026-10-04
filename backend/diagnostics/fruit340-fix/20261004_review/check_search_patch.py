"""Check new optional search against frozen2D paths and actual308..311 pairs."""
from pathlib import Path
exec((Path(__file__).resolve().parent/'review_rotation.py').read_text().split("report = ")[0])
spec=importlib.util.spec_from_file_location('production_search_patch',ROOT/'algorithm.py')
production=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=production
spec.loader.exec_module(production)
report={'two_axis_parity':[],'three_axis_pairs':[]}
for index,source in enumerate(views[:-1]):
    if source.frame_index not in (305,306,307,308,309,310,311,312,313,315,316,324,337,340,350,360):
        continue
    target=views[index+1]
    pm=alg._subset_spheroid(model,[index,index+1])
    settings=replace(s,image_downsample=1,highpass_sigma=5.,matching_cost='aligned_mad',min_pair_angle_deg=0.)
    results=[]
    for module in (alg,production):
        try:
            rotation,error=module._search_rotation(source,target,pm,0,settings)
            results.append((rotation,error,None))
        except module.MappingError as exc:
            results.append((None,None,str(exc)))
    if results[0][0] is not None and results[1][0] is not None:
        same=bool(np.array_equal(results[0][0],results[1][0]) and results[0][1]==results[1][1])
    else:
        same=results[0][2]==results[1][2]
    report['two_axis_parity'].append({'source_frame':source.frame_index,'same':same})
    if source.frame_index in (308,309,310,311):
        pair={'source_frame':source.frame_index,'target_frame':target.frame_index}
        rotations={}
        reversepm=alg._subset_spheroid(model,[index+1,index])
        for name,v1,v2,fitted,st in (
            ('joint',source,target,pm,settings),
            ('forward',source,target,pm,replace(settings,bidirectional_matching=False)),
            ('reverse',target,source,reversepm,replace(settings,bidirectional_matching=False,rotation_direction=-s.rotation_direction))):
            try:
                rotation,error=production._search_rotation(v1,v2,fitted,0,st,inplane_angle_deg=10.)
                rotations[name]=rotation
                pair[name]={'rotation_vector_deg':np.rad2deg(cv2.Rodrigues(rotation)[0]).ravel().tolist(),'residual':error}
            except production.MappingError as exc:
                pair[name]={'reason':str(exc)}
        if 'forward' in rotations and 'reverse' in rotations:
            pair['independent_inverse_disagreement_deg']=float(np.linalg.norm(np.rad2deg(cv2.Rodrigues(rotations['reverse']@rotations['forward'])[0])))
        report['three_axis_pairs'].append(pair)
        print(json.dumps(pair),flush=True)
report['two_axis_bit_identical']=all(r['same'] for r in report['two_axis_parity'])
(OUT/'search_patch_check.json').write_text(json.dumps(report,indent=2))
print('2D parity',report['two_axis_bit_identical'],flush=True)
