# -*- coding: utf-8 -*-

###########################################################################
#    OCRFeeder - The complete OCR suite
#    Copyright (C) 2009 Joaquim Rocha
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
###########################################################################

import tempfile
from util.lib import debug

import gettext
import Image, ImageDraw
import os.path
from util import graphics
import sys

_ = gettext.gettext

class ImageProcessor:

    def __init__(self, path_to_image,
                 window_size = None, contrast_tolerance = 120):
        self.window_size = window_size
        self.contrast_tolerance = contrast_tolerance
        error_message = _("A problem occurred while trying to open the image:\n %s\n"
                          "Ensure the image exists or try converting it to another format.") % path_to_image
        if os.path.isfile(path_to_image):
            try:
                self.original_image = Image.open(path_to_image)
                self.black_n_white_image = self.original_image.convert('L')
                if not self.window_size:
                    self.window_size = self.original_image.size[1] / 60.
                debug('Window Size: ', self.window_size)
            except:
                debug(sys.exc_info())
                raise ImageManipulationError(error_message)
        else:
            debug(sys.exc_info())
            raise ImageManipulationError(error_message)
        self.bg_color = 255

    def __windowContrast(self, bgcolor, x, y):
        image = self.black_n_white_image
        width, height = image.size

        image_upper_left_corner_x = x * self.window_size
        image_upper_left_corner_y = y * self.window_size

        i, j = 1, 1
        while j < self.window_size + 1:
            if not image_upper_left_corner_y + j < height:
                break
            while i < self.window_size + 1:
                if not image_upper_left_corner_x + i < width:
                    break
                pixel_point = (image_upper_left_corner_x + i,
                               image_upper_left_corner_y + j)
                if graphics.colorsContrast(image.getpixel(pixel_point),
                                           bgcolor,
                                           self.contrast_tolerance):
                    return 1
                i += 3
            i = 1
            j += 3
        return 0

    def imageToBinary(self):
        image = self.black_n_white_image
        binary_info = ['']
        width, height = image.size
        i, j = 0, 0
        while j < height / self.window_size:
            while i < width / self.window_size:
                binary_info[-1] += str(self.__windowContrast(self.bg_color, i, j))
                i += 1
            i = 0
            binary_info += ['']
            j += 1
        return binary_info

class Slicer:

    def __init__(self, original_image, temp_dir = '/tmp'):
        self.original_image = original_image
        self.temp_dir = temp_dir

    def slice(self, bounding_box):
        return self.original_image.crop(bounding_box)

    def sliceFromPointsList(self, points_list):
        if len(points_list) < 3:
            raise InsuficientPointsForPolygon
        bounding_box = graphics.getContainerRectangle(points_list)
        return self.original_image.crop(bounding_box)

    def sliceFromBlock(self, block, window_size):
        cropped_image = self.slice(block.translateToUnits(window_size))
        image_file = tempfile.mkstemp(dir = self.temp_dir)[1]
        cropped_image.save(image_file, format = 'PNG')

class ContentAnalyser:

    def __init__(self, image):
        self.image = image

    def getHeight(self):
        width, height = self.image.size
        image_draw = ImageDraw.Draw(self.image)
        i = 0
        while i+3 < height:
            current_line_image = self.image.crop((0, i, width, i + 3))
            if len(current_line_image.getcolors()) < 10:
                image_draw.rectangle((0, i, width, i + 3), fill = (255, 255, 255))
            i += 3

    def __getBlankSpaceFromTopToBottom(self, image):
        width, height = image.size
        i = 0
        while i + 2 < height:
            current_line_image = image.crop((0, i, width, i + 1))
            if len(current_line_image.getcolors()) > 1:
                break
            i += 2
        return i

class ImageManipulationError(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value

class InsuficientPointsForPolygon(Exception):

    def __init__(self):
        pass

    def __str__(self):
        return 'Insufficient number of points for polygon. Must be at least three points.'
