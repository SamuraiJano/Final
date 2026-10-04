"""Independent checks of benchmark forward/backward reprojection math."""
import unittest

import cv2
import numpy as np

from algorithm import Ellipse, MappingError, Spheroid
from benchmark_authors import predict_point, stats


class BenchmarkMeasurementTests(unittest.TestCase):
    def test_noncommuting_rotations_and_reverse_correspondence(self):
        radius = 100.
        centers = [np.array([120.,130.]), np.array([121.,128.]), np.array([117.,132.])]
        ellipses = [Ellipse(c,radius,radius,np.array([1.,0.]),np.array([0.,1.])) for c in centers]
        model = Spheroid(radius,radius,ellipses,[np.eye(3)/radius**2]*3,
                         np.eye(3),0,[np.array([0.,1.,0.])]*3)
        a, b = np.deg2rad(20), np.deg2rad(-15)
        # Explicit analytical matrices, independent of the benchmark's Rodrigues calls.
        rx = np.array([[1,0,0],[0,np.cos(a),-np.sin(a)],[0,np.sin(a),np.cos(a)]])
        ry = np.array([[np.cos(b),0,np.sin(b)],[0,1,0],[-np.sin(b),0,np.cos(b)]])
        source = np.array([10.,15.,np.sqrt(radius**2-10**2-15**2)])
        target = ry @ (rx @ source)
        row = {'source':0,'target':2,'source_xy':(source[:2]+centers[0]).tolist()}
        prediction = predict_point(row,model,{0:rx,1:ry})
        np.testing.assert_allclose(prediction,target[:2]+centers[2],atol=1e-10)
        back = {'source':2,'target':0,'source_xy':prediction.tolist()}
        np.testing.assert_allclose(predict_point(back,model,{0:rx,1:ry}),row['source_xy'],atol=1e-10)
        with self.assertRaisesRegex(MappingError,'Missing accepted rotation'):
            predict_point(row,model,{0:rx})

    def test_rms_is_not_mean_distance(self):
        result=stats([3,4])
        self.assertAlmostEqual(result['rms'],np.sqrt(12.5))
        self.assertEqual(result['mean'],3.5)


if __name__ == '__main__':
    unittest.main()
