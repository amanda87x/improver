# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# (C) British Crown Copyright 2017 Met Office.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
"""Utilities for using neighbourhood processing."""

import numpy as np
import numpy.ma as ma

import iris

from improver.nbhood.nbhood import NeighbourhoodProcessing
from improver.utilities.cube_checker import (
    check_cube_coordinates, find_dimension_coordinate_mismatch)
from improver.blending.weights import WeightsUtilities


class ApplyNeighbourhoodProcessingWithAMask(object):

    """Class for applying neighbourhood processing when passing in a mask
    cube that is iterated over."""

    def __init__(
            self, coord_for_masking, radii,
            lead_times=None, ens_factor=1.0, weighted_mode=True,
            sum_or_fraction="fraction", re_mask=False):
        """
        Initialise the class.

        Args:
            coord_for_masking (string):
                String matching the name of the coordinate that will be used
                for masking.
            radii (float or List if defining lead times):
                The radii in metres of the neighbourhood to apply.
                Rounded up to convert into integer number of grid
                points east and north, based on the characteristic spacing
                at the zero indices of the cube projection-x and y coords.

        Keyword Args:
            lead_times (None or List):
                List of lead times or forecast periods, at which the radii
                within 'radii' are defined. The lead times are expected
                in hours.
            ens_factor (float):
                The factor with which to adjust the neighbourhood size
                for more than one ensemble member.
                If ens_factor = 1.0 this essentially conserves ensemble
                members if every grid square is considered to be the
                equivalent of an ensemble member.
                Optional, defaults to 1.0
            weighted_mode (boolean):
                If True, use a circle for neighbourhood kernel with
                weighting decreasing with radius.
                If False, use a circle with constant weighting.
            sum_or_fraction (string):
                Identifier for whether sum or fraction should be returned from
                neighbourhooding. The sum represents the sum of the
                neighbourhood.
                The fraction represents the sum of the neighbourhood divided by
                the neighbourhood area. "fraction" is the default.
                Valid options are "sum" or "fraction".
            re_mask (boolean):
                If re_mask is True, the original un-neighbourhood processed
                mask is applied to mask out the neighbourhood processed cube.
                If re_mask is False, the original un-neighbourhood processed
                mask is not applied. Therefore, the neighbourhood processing
                may result in values being present in areas that were
                originally masked.
        """
        self.coord_for_masking = coord_for_masking
        self.neighbourhood_method = "square"
        self.radii = radii
        self.lead_times = lead_times
        self.ens_factor = ens_factor
        self.weighted_mode = weighted_mode
        self.sum_or_fraction = sum_or_fraction
        self.re_mask = re_mask

    def __repr__(self):
        """Represent the configured plugin instance as a string."""
        result = ('<ApplyNeighbourhoodProcessingWithAMask: '
                  'coord_for_masking: {}, neighbourhood_method: {}, '
                  'radii: {}, lead_times: {}, ens_factor: {}, '
                  'weighted_mode: {}, sum_or_fraction: {}, re_mask: {}>')
        return result.format(
            self.coord_for_masking, self.neighbourhood_method, self.radii,
            self.lead_times, self.ens_factor, self.weighted_mode,
            self.sum_or_fraction, self.re_mask)

    def process(self, cube, mask_cube):
        """
        1. Iterate over the chosen coordinate within the mask_cube and apply
           the mask at each iteration to the cube that is to be neighbourhood
           processed.
        2. Concatenate the cubes from each iteration together to create a
           single cube.

        Args:
            cube (Iris.cube.Cube):
                Cube containing the array to which the square neighbourhood
                will be applied.
            mask_cube (Iris.cube.Cube):
                Cube containing the array to be used as a mask.

        Returns:
            concatenated_cube (Iris.cube.Cube):
                Cube containing the smoothed field after the square
                neighbourhood method has been applied when applying masking
                for each point along the coord_for_masking coordinate.
                The resulting cube is concatenated so that the dimension
                coordinates match the input cube.

        """
        yname = cube.coord(axis='y').name()
        xname = cube.coord(axis='x').name()
        result_slices = iris.cube.CubeList([])
        # Take 2D slices of the input cube for memory issues.
        for x_y_slice in cube.slices([yname, xname]):
            cube_slices = iris.cube.CubeList([])
            # Apply each mask in in mask_cube to the 2D input slice.
            for cube_slice in mask_cube.slices_over(self.coord_for_masking):
                output_cube = NeighbourhoodProcessing(
                    self.neighbourhood_method, self.radii,
                    lead_times=self.lead_times,
                    weighted_mode=self.weighted_mode,
                    ens_factor=self.ens_factor,
                    sum_or_fraction=self.sum_or_fraction, re_mask=self.re_mask
                    ).process(x_y_slice, mask_cube=cube_slice)
                coord_object = cube_slice.coord(self.coord_for_masking).copy()
                output_cube.add_aux_coord(coord_object)
                output_cube = iris.util.new_axis(
                    output_cube, self.coord_for_masking)
                cube_slices.append(output_cube)
            concatenated_cube = cube_slices.concatenate_cube()
            exception_coordinates = (
                find_dimension_coordinate_mismatch(
                    x_y_slice, concatenated_cube, two_way_mismatch=False))
            concatenated_cube = check_cube_coordinates(
                x_y_slice, concatenated_cube,
                exception_coordinates=exception_coordinates)
            result_slices.append(concatenated_cube)
        result = result_slices.merge_cube()
        exception_coordinates = (
            find_dimension_coordinate_mismatch(
                cube, result, two_way_mismatch=False))
        result = check_cube_coordinates(
            cube, result,
            exception_coordinates=exception_coordinates)

        return result


class CollapseMaskedNeighbourhoodCoordinate(object):

    """
    Plugin for collapsing the coordinate the mask was applied to after
    masked neighbourhood processing.

    Takes into account the result from the neighbourhood processing to
    adjust the weights between the bands in the coordinate for the points
    where the were no points within a neighbourhood for and a non-zero
    weighting.
    """

    def __init__(self, coord_masked, weights=None):
        """
        Initialise the class.

        Args:
            coord_masked (string):
                String matching the name of the coordinate that has been used
                for masking.

        Keyword Args:
            weights (cube):
                A cube from an ancillary file containing the weights for each
                point in the coord_masked at each grid point. Only two points
                in coord_masked can have a non-zero weight for each grid-point,
                i.e. we are only weighting between two adjacent bands in the
                neighbourhood output for each gridpoint.
                Should have the coordinates coord_masked, x and y.
                Default is None which equal weights for each band in the mean
                used to collapse the chosen coordinate.
                The weights cube can be masked, and this mask will be retained,
                and will be present in the output.
.
        """
        self.coord_masked = coord_masked
        self.weights = weights

    def __repr__(self):
        """Represent the configured plugin instance as a string."""
        result = ('<ApplyNeighbourhoodProcessingWithAMask: '
                  'coord_masked: {}, weights: {}>')
        return result.format(self.coord_masked,
                             self.weights)

    def reweight_weights(self, nbhood_cube):
        """
        Reweight the weights taking into account where there are NaNs in the
        result from neighbourhood.

        The weights corresponding to NaNs in the result from neighbourhooding
        with a mask are set to zero and then the weights are renormalized along
        the axis corresponding to the coordinate we want to collapse.

        Args:
            nbhood_cube (iris.cube.Cube):
                The cube that has been through masked neighbourhood processing
                and has the dimension we wish to collapse. Must have the same
                dimensions of the cube.
        """
        # If the weights are masked we want to retain the mask.
        condition = np.isnan(nbhood_cube.data)
        if ma.is_masked(self.weights.data):
            condition = condition & ~self.weights.data.mask

        self.weights.data[condition] = 0.0
        axis = nbhood_cube.coord_dims(self.coord_masked)
        self.weights.data = WeightsUtilities.normalise_weights(
            self.weights.data, axis=axis)

    def process(self, cube):
        """
        Collapse the chosen coordinates with the available weights. The result
        of the neighbourhood processing is taken into account to reweight any
        weights corresponding to a NaN in the result from neighbourhooding. In
        this case the weights are re-normalized so that we do not lose
        probability.

        Args:
            cube (Iris.cube.Cube):
                Cube containing the array to which the square neighbourhood
                with a mask has been applied.

        Returns:
            result (Iris.cube.Cube):
                Cube containing the weighted result from neighbourhood after
                collapsing the chosen coordinate.

        """
        # Mask out any NaNs in the neighbourhood data so that Iris ignores
        # them when calculating the weighted mean.
        cube.data = ma.masked_invalid(cube.data)
        # Take into account the case that the weights might be None and not
        # a cube.
        yname = cube.coord(axis='y').name()
        xname = cube.coord(axis='x').name()

        if isinstance(self.weights, iris.cube.Cube):
            if self.weights.shape != cube.shape:
                first_slice = next(
                    cube.slices([self.coord_masked, yname, xname],
                                ordered=False))
                self.reweight_weights(first_slice)
            else:
                self.reweight_weights(cube)
            weights = self.weights.data
        else:
            weights = self.weights

        cubelist = iris.cube.CubeList([])
        for slice_3d in cube.slices([self.coord_masked, yname, xname]):
            # Loop over any extra dimensions
            collapsed_slice = slice_3d.collapsed(
                self.coord_masked, iris.analysis.MEAN, weights=weights)
            cubelist.append(collapsed_slice)
        result = cubelist.merge_cube()
        # Promote any scalar coordinates with one point back to dimension
        # coordinates if they were dimensions in the input cube.
        # Take a slice over the coordinate we are collapsing as we do not
        # expect this in the output cube.
        first_slice = next(cube.slices_over([self.coord_masked]))
        result = check_cube_coordinates(first_slice, result)
        # Remove any reference to the coordinate we have collapsed.
        result.remove_coord(self.coord_masked)
        new_cell_methods = [cell_method for cell_method in result.cell_methods
                            if cell_method.coord_names != (self.coord_masked,)]
        result.cell_methods = tuple(new_cell_methods)
        # TODO fix any metadata problems here.
        return result
