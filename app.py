#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import base64
import cStringIO
import sys
import tempfile
import io
import math

MODEL_BASE = '/opt/models/research'
sys.path.append(MODEL_BASE)
sys.path.append(MODEL_BASE + '/object_detection')
sys.path.append(MODEL_BASE + '/slim')

from decorator import requires_auth
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_api import FlaskAPI
from flask_wtf.file import FileField
import numpy as np
from PIL import Image
from PIL import ImageDraw
import tensorflow as tf
from utils import label_map_util
from utils import visualization_utils as vis_util
from werkzeug.datastructures import CombinedMultiDict
from wtforms import Form
from wtforms import ValidationError

app = FlaskAPI(__name__)


@app.before_request
@requires_auth
def before_request():
    pass


PATH_TO_CKPT = '/opt/graph_def/frozen_inference_graph.pb'
PATH_TO_LABELS = '/home/comecloserandseee/letter-label-map.pbtxt'

content_types = {'jpg': 'image/jpeg',
                 'jpeg': 'image/jpeg',
                 'png': 'image/png'}
extensions = sorted(content_types.keys())


def is_image():
    def _is_image(form, field):
        if not field.data:
            raise ValidationError()
        elif field.data.filename.split('.')[-1].lower() not in extensions:
            raise ValidationError()

    return _is_image


class PhotoForm(Form):
    input_photo = FileField(
        'File extension should be: %s (case-insensitive)' % ', '.join(extensions),
        validators=[is_image()])


class ObjectDetector(object):
    MIN_SCORE = .1

    def __init__(self):
        self.detection_graph = self._build_graph()
        self.sess = tf.Session(graph=self.detection_graph)

        label_map = label_map_util.load_labelmap(PATH_TO_LABELS)
        categories = label_map_util.convert_label_map_to_categories(
            label_map, max_num_classes=90, use_display_name=True)
        self.category_index = label_map_util.create_category_index(categories)

    def _build_graph(self):
        detection_graph = tf.Graph()
        with detection_graph.as_default():
            od_graph_def = tf.GraphDef()
            with tf.gfile.GFile(PATH_TO_CKPT, 'rb') as fid:
                serialized_graph = fid.read()
                od_graph_def.ParseFromString(serialized_graph)
                tf.import_graph_def(od_graph_def, name='')

        return detection_graph

    def _load_image_into_numpy_array(self, image):
        (im_width, im_height) = image.size
        return np.array(image.getdata()).reshape(
            (im_height, im_width, 3)).astype(np.uint8)

    def detect(self, image):
        image_np = self._load_image_into_numpy_array(image)
        image_np_expanded = np.expand_dims(image_np, axis=0)

        graph = self.detection_graph
        image_tensor = graph.get_tensor_by_name('image_tensor:0')
        boxes = graph.get_tensor_by_name('detection_boxes:0')
        scores = graph.get_tensor_by_name('detection_scores:0')
        classes = graph.get_tensor_by_name('detection_classes:0')
        num_detections = graph.get_tensor_by_name('num_detections:0')

        (boxes, scores, classes, num_detections) = self.sess.run(
            [boxes, scores, classes, num_detections],
            feed_dict={image_tensor: image_np_expanded})

        boxes, scores, classes, num_detections = map(
            np.squeeze, [boxes, scores, classes, num_detections])

        return boxes, scores, classes.astype(int), num_detections

    def _encode_image(self, image):
        image_buffer = cStringIO.StringIO()
        image.save(image_buffer, format='PNG')
        imgstr = 'data:image/png;base64,{:s}'.format(
            base64.b64encode(image_buffer.getvalue()))
        return imgstr

    def detect_all_objects(self, image_path):
        image = Image.open(image_path).convert('RGB')
        im_width, im_height = image.size

        boxes, scores, classes, num_detections = self.detect(image)
        image_np = self._load_image_into_numpy_array(image)
        vis_util.visualize_boxes_and_labels_on_image_array(
            image_np,
            boxes,
            classes,
            scores,
            self.category_index,
            use_normalized_coordinates=True,
            min_score_thresh=self.MIN_SCORE,
            line_thickness=2)

        img = Image.fromarray(image_np, 'RGB')
        result = {}
        result['original'] = self._encode_image(img.copy())

        lines = dict()
        cols = dict()
        for i in range(num_detections):
            if scores[i] < self.MIN_SCORE: continue
            cls = classes[i]
            ymin, xmin, ymax, xmax = boxes[i]
            (left, right, top, bottom) = (round(xmin * im_width), round(xmax * im_width),
                                          round(ymin * im_height), round(ymax * im_height))
            self.add_line_symbol(lines, top, left, bottom, right, cls, scores[i])
            self.add_col_symbol(cols, top, left, bottom, right, cls, scores[i])

        result['lines'] = self.get_res_lines(lines)
        result['cols'] = self.get_res_cols(cols)

        return result

    def add_line_symbol(self, lines, top, left, bottom, right, cls, score):
        if len(lines) == 0:
            lines[int(top)] = {}
            lines[int(top)][int(left)] = {}
            lines[int(top)][int(left)] = {
                'label': self.category_index[cls]['name'],
                'top': str(top),
                'left': str(left),
                'bottom': str(bottom),
                'right': str(right),
                'scores': str(score)
            }
        else:
            foundLine = False
            for lineTop in lines.keys():
                if math.fabs(lineTop - top) < 20:
                    foundLine = True
                    foundLeft = False
                    for lineLeft in lines[lineTop].keys():
                        if math.fabs(lineLeft - left) < 5:
                            foundLeft = True
                            if score > float(lines[lineTop][lineLeft]['scores']):
                                lines[lineTop][lineLeft] = {
                                    'label': client.category_index[cls]['name'],
                                    'top': str(top),
                                    'left': str(left),
                                    'bottom': str(bottom),
                                    'right': str(right),
                                    'scores': str(score)
                                }
                            break

                    if foundLeft == False:
                        lines[lineTop][int(left)] = {}
                        lines[lineTop][int(left)] = {
                            'label': client.category_index[cls]['name'],
                            'top': str(top),
                            'left': str(left),
                            'bottom': str(bottom),
                            'right': str(right),
                            'scores': str(score)
                        }
                    break
            if foundLine == False:
                lines[int(top)] = {}
                lines[int(top)][int(left)] = {}
                lines[int(top)][int(left)] = {
                    'label': client.category_index[cls]['name'],
                    'top': str(top),
                    'left': str(left),
                    'bottom': str(bottom),
                    'right': str(right),
                    'scores': str(score)
                }

    def add_col_symbol(self, cols, top, left, bottom, right, cls, score):
        if len(cols) == 0:
            cols[int(left)] = {}
            cols[int(left)][int(top)] = {}
            cols[int(left)][int(top)] = {
                'label': client.category_index[cls]['name'],
                'top': str(top),
                'left': str(left),
                'bottom': str(bottom),
                'right': str(right),
                'scores': str(score)
            }
        else:
            foundCol = False
            for colLeft in cols.keys():
                if math.fabs(colLeft - left) < 80:
                    foundCol = True
                    foundTop = False
                    for colTop in cols[colLeft].keys():
                        if math.fabs(colTop - top) <= 5:
                            foundTop = True
                            if score > float(cols[colLeft][colTop]['scores']):
                                cols[colLeft][colTop] = {
                                    'top': str(top),
                                    'left': str(left),
                                    'bottom': str(bottom),
                                    'right': str(right),
                                    'label': client.category_index[cls]['name'],
                                    'scores': str(score)
                                }
                            break

                    if foundTop == False:
                        cols[colLeft][int(top)] = {}
                        cols[colLeft][int(top)] = {
                            'top': str(top),
                            'left': str(left),
                            'bottom': str(bottom),
                            'right': str(right),
                            'label': client.category_index[cls]['name'],
                            'scores': str(score)
                        }
                    break
            if foundCol == False:
                cols[int(left)] = {}
                cols[int(left)][int(top)] = {}
                cols[int(left)][int(top)] = {
                    'top': str(top),
                    'left': str(left),
                    'bottom': str(bottom),
                    'right': str(right),
                    'label': client.category_index[cls]['name'],
                    'scores': str(score)
                }

    def get_res_lines(self, lines):
        resLines = []
        for key, line in sorted(lines.items()):
            if len(line) >= 3:
                resLine = ""
                for lineKey, lineElem in sorted(line.items()):
                    resLine += lineElem['label']
                resLines.append(resLine)
        return resLines

    def get_res_lines_with_coords(self, lines):
        resLines = dict()
        for key, line in sorted(lines.items()):
            if len(line) >= 3:
                resLine = []
                resLineId = ""
                for lineKey, lineElem in sorted(line.items()):
                    resLineId += lineElem['label']
                    resLine.append(lineElem['label']
                                   + "," + lineElem['left'].rstrip('0').rstrip('.')
                                   + "," + lineElem['top'].rstrip('0').rstrip('.')
                                   + "," + lineElem['right'].rstrip('0').rstrip('.')
                                   + "," + lineElem['bottom'].rstrip('0').rstrip('.'))

                resLines[resLineId] = resLine
        return resLines

    def get_res_cols(self, cols):
        resCols = []
        for key, col in sorted(cols.items()):
            if len(col) >= 3:
                resCol = ""
                for colKey, colElem in sorted(col.items()):
                    resCol += colElem['label']
                resCols.append(resCol)
        return resCols

    def get_res_cols_with_coords(self, cols):
        resCols = dict()
        for key, col in sorted(cols.items()):
            if len(col) >= 3:
                resCol = []
                resColId = ""
                for colKey, colElem in sorted(col.items()):
                    resColId += colElem['label']
                    resCol.append(colElem['label']
                                  + "," + colElem['left'].rstrip('0').rstrip('.')
                                  + "," + colElem['top'].rstrip('0').rstrip('.')
                                  + "," + colElem['right'].rstrip('0').rstrip('.')
                                  + "," + colElem['bottom'].rstrip('0').rstrip('.'))
                resCols[resColId] = resCol
        return resCols


def draw_bounding_box_on_image(image, box, color='red', thickness=4):
    draw = ImageDraw.Draw(image)
    im_width, im_height = image.size
    ymin, xmin, ymax, xmax = box
    (left, right, top, bottom) = (xmin * im_width, xmax * im_width,
                                  ymin * im_height, ymax * im_height)
    draw.line([(left, top), (left, bottom), (right, bottom),
               (right, top), (left, top)], width=thickness, fill=color)


def encode_image(image):
    image_buffer = cStringIO.StringIO()
    image.save(image_buffer, format='PNG')
    imgstr = 'data:image/png;base64,{:s}'.format(
        base64.b64encode(image_buffer.getvalue()))
    return imgstr


def detect_objects(image_path):
    image = Image.open(image_path).convert('RGB')
    boxes, scores, classes, num_detections = client.detect(image)
    image.thumbnail((480, 480), Image.ANTIALIAS)

    new_images = {}
    for i in range(num_detections):
        if scores[i] < 0.3: continue
        cls = classes[i]
        if cls not in new_images.keys():
            new_images[cls] = image.copy()
        draw_bounding_box_on_image(new_images[cls], boxes[i],
                                   thickness=int(scores[i] * 10) - 4)

    result = {}
    result['original'] = encode_image(image.copy())

    for cls, new_image in new_images.iteritems():
        category = client.category_index[cls]['name']
        result[category] = encode_image(new_image)

    return result


@app.route('/')
def upload():
    photo_form = PhotoForm(request.form)
    return render_template('upload.html', photo_form=photo_form, result={})


@app.route('/post', methods=['GET', 'POST'])
def post():
    form = PhotoForm(CombinedMultiDict((request.files, request.form)))
    if request.method == 'POST' and form.validate():
        with tempfile.NamedTemporaryFile() as temp:
            form.input_photo.data.save(temp)
            temp.flush()
            result = client.detect_all_objects(temp.name)

        photo_form = PhotoForm(request.form)
        return render_template('upload.html',
                               photo_form=photo_form, result=result)
    else:
        return redirect(url_for('upload'))


@app.route("/detect", methods=['POST'])
def detect_by_api():
    result = dict()
    imgstring = request.data.get('detect_image', 'f')
    if imgstring != 'f':
        imgdata = base64.b64decode(imgstring)
        image = Image.open(io.BytesIO(imgdata)).convert('RGB')
        im_width, im_height = image.size
        boxes, scores, classes, num_detections = client.detect(image)

        lines = dict()
        cols = dict()
        for i in range(num_detections):
            if scores[i] < client.MIN_SCORE: continue
            cls = classes[i]
            ymin, xmin, ymax, xmax = boxes[i]
            (left, right, top, bottom) = (round(xmin * im_width), round(xmax * im_width),
                                          round(ymin * im_height), round(ymax * im_height))
            client.add_line_symbol(lines, top, left, bottom, right, cls, scores[i])
            client.add_col_symbol(cols, top, left, bottom, right, cls, scores[i])

        result['lines'] = client.get_res_lines(lines)
        result['cols'] = client.get_res_cols(cols)
    else:
        result['error'] = 'no image found'
    return result


@app.route("/detect-with-coords", methods=['POST'])
def detect_by_api_with_coords():
    result = dict()
    imgstring = request.data.get('detect_image', 'f')
    if imgstring != 'f':
        imgdata = base64.b64decode(imgstring)
        image = Image.open(io.BytesIO(imgdata)).convert('RGB')
        im_width, im_height = image.size
        boxes, scores, classes, num_detections = client.detect(image)

        lines = dict()
        cols = dict()
        for i in range(num_detections):
            if scores[i] < client.MIN_SCORE: continue
            cls = classes[i]
            ymin, xmin, ymax, xmax = boxes[i]
            (left, right, top, bottom) = (round(xmin * im_width), round(xmax * im_width),
                                          round(ymin * im_height), round(ymax * im_height))
            client.add_line_symbol(lines, top, left, bottom, right, cls, scores[i])
            client.add_col_symbol(cols, top, left, bottom, right, cls, scores[i])

        result['lines'] = client.get_res_lines_with_coords(lines)
        result['cols'] = client.get_res_cols_with_coords(cols)
    else:
        result['error'] = 'no image found'
    return result


client = ObjectDetector()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
