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

from customWidgets import SelectableBoxesArea
from dataHolder import DataBox, PageData, TEXT_TYPE, IMAGE_TYPE
from feeder.documentGeneration import OdtGenerator, HtmlGenerator
from feeder.imageManipulation import *
from feeder.layoutAnalysis import *
from pango import FontDescription, SCALE
from studio.configuration import ProjectSaver, ProjectLoader
from util import graphics, ALIGN_LEFT, ALIGN_RIGHT, ALIGN_CENTER, ALIGN_FILL, \
    PAPER_SIZES
from util.lib import debug
from util import constants
from util.asyncworker import AsyncItem
from widgetPresenter import BoxEditor, PagesToExportDialog, FileDialog, \
    PageSizeDialog, getPopupMenu, WarningDialog, UnpaperDialog, \
    QueuedEventsProgressDialog
import gettext
import gobject
import gtk
import math
import os.path
import pygtk
import threading
import sys
pygtk.require('2.0')
_ = gettext.gettext



class SourceImagesSelector(gobject.GObject):

    __gtype_name__ = 'SourceImagesSelector'

    __gsignals__ = {
        'selection_changed' : (gobject.SIGNAL_RUN_LAST,
                     gobject.TYPE_NONE,
                     (gobject.TYPE_BOOLEAN,))
        }

    def __init__(self, list_of_images = []):
        super(SourceImagesSelector, self).__init__()
        self.list_store = gtk.ListStore(str, str, gtk.gdk.Pixbuf)
        if len(list_of_images):
            for path in list_of_images:
                self.__renderImage(path, self.__generateImageName(path))

    def addImage(self, path):
        image_name = self.__generateImageName(path)
        return self.__renderImage(path, image_name)

    def __renderImage(self, path, image_name):
        path = os.path.abspath(os.path.expanduser(path))
        try:
            pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(path, 150, 100)
        except:
            return
        iter = self.list_store.append([path, image_name, pixbuf])
        self.emit('selection_changed', self.isEmpty())
        return pixbuf, path, iter

    def __countEqualPathsStored(self, path):
        iter = self.list_store.get_iter_root()
        counter = 0
        while iter != None:
            image_path = self.list_store.get_value(iter, 0)
            if image_path == path:
                counter += 1
            iter = self.list_store.iter_next(iter)
        return counter

    def __generateImageName(self, path):
        image_name = os.path.basename(path)
        number_of_equal_paths = self.__countEqualPathsStored(path)
        if number_of_equal_paths:
            image_name += ' ('+ str(number_of_equal_paths + 1) + ')'
        return image_name

    def getPixbufAtPath(self, path):
        iter = self.list_store.get_iter(path)
        return self.list_store.get_value(iter, 2)

    def getPixbufsSorted(self):
        pixbufs = []
        iter = self.list_store.get_iter_root()
        while iter != None:
            pixbufs.append(self.list_store.get_value(iter, 2))
            iter = self.list_store.iter_next(iter)
        return pixbufs

    def removeIter(self, path):
        iter = self.list_store.get_iter(path)
        self.list_store.remove(iter)
        self.emit('selection_changed', self.isEmpty())

    def clear(self):
        self.list_store.clear()
        self.emit('selection_changed', self.isEmpty())

    def isEmpty(self):
        return self.list_store.get_iter_first() == None

class SourceImagesSelectorIconView(gtk.IconView):

    def __init__(self, source_images_selector):
        self.source_images_selector = source_images_selector
        super(SourceImagesSelectorIconView, self).__init__(self.source_images_selector.list_store)
        self.get_accessible().set_name(_('Pages'))
        self.set_text_column(1)
        self.set_pixbuf_column(2)
        self.set_orientation(gtk.ORIENTATION_VERTICAL)
        self.set_columns(1)
        self.set_reorderable(True)
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.set_selection_mode(gtk.SELECTION_BROWSE)
        self.connect('button-press-event', self.pressedRightButton)

    def pressedRightButton(self, target, event):
        if event.button == 3:
            selected_items = self.get_selected_items()
            if selected_items:
                menu = getPopupMenu([(gtk.STOCK_DELETE, _('Delete'), self.delete_current_page_function)])
                menu.popup(None, None, None, event.button, event.time)

    def getSelectedPixbuf(self):
        selected_items = self.get_selected_items()
        if len(selected_items):
            selected_item_path = selected_items[0]
            return self.source_images_selector.getPixbufAtPath(selected_item_path)
        return None

    def setDeleteCurrentPageFunction(self, function):
        self.delete_current_page_function = function

    def deleteCurrentSelection(self):
        selected_items = self.get_selected_items()
        if len(selected_items):
            selected_item_path = selected_items[0]
            self.source_images_selector.removeIter(selected_item_path)
            if not self.source_images_selector.isEmpty():
                self.select_path(0)

    def clear(self):
        self.source_images_selector.clear()


class ImageReviewer:

    def __init__(self, main_window, path_to_image, ocr_engines):
        self.main_window = main_window
        self.path_to_image = path_to_image
        self.text_box_fill_color = (94, 156, 235, 150)
        self.box_stroke_color = (94, 156, 235, 250)
        self.image_box_fill_color = (0, 183, 0, 150)
        self.selectable_boxes_area = SelectableBoxesArea(self.path_to_image)
        self.selectable_boxes_area.connect('selected_box', self.selectedBox)
        self.selectable_boxes_area.connect('removed_box', self.removedBox)
        self.selectable_boxes_area.connect('updated_box', self.updatedBox)
        self.selectable_boxes_area.connect('dragged_box', self.updatedBoxBounds)
        self.selectable_boxes_area.connect('deselected_box',
                                           self.deselectedBoxCb)
        self.image_pixbuf = gtk.gdk.pixbuf_new_from_file(self.path_to_image)
        self.reviewer_area = gtk.HPaned()
        self.reviewer_area.set_position(500)
        self.reviewer_area.show()
        self.boxeditor_notebook = gtk.Notebook()
        self.boxeditor_notebook.set_show_tabs(False)
        self.boxeditor_notebook.set_show_border(False)
        self.boxeditor_notebook.show()

        selectable_boxes_scrolled_window = gtk.ScrolledWindow()
        selectable_boxes_scrolled_window.get_accessible().set_name(
                                                         _('Selectable areas'))
        selectable_boxes_scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        selectable_boxes_scrolled_window.add(self.selectable_boxes_area)
        self.selectable_boxes_area.show()
        selectable_boxes_scrolled_window.show()

        self.reviewer_area.pack1(selectable_boxes_scrolled_window, True, False)
        self.reviewer_area.pack2(self.boxeditor_notebook, True, False)
        self.ocr_engines = ocr_engines
        self.editor_list = []
        self.page = PageData(self.path_to_image)

        selectable_boxes_scrolled_window.connect_after("size-allocate", self.zoomFitCb)

    def setTextFillColor(self, color):
        self.text_box_fill_color = color
        self.selectable_boxes_area.setAreaFillRgba(self.text_box_fill_color)

    def setBoxesStrokeColor(self, color):
        self.box_stroke_color = color
        self.selectable_boxes_area.setAreaStrokeRgba(self.box_stroke_color)

    def setImageFillColor(self, color):
        self.image_box_fill_color = color

    def addBoxEditor(self, box):
        editor = Editor(box, self.image_pixbuf, self.ocr_engines, self)
        self.editor_list.append(editor)
        self.boxeditor_notebook.append_page(editor.box_editor)
        return editor

    def selectedBox(self, widget, box):
        page_num = self.__getPageNumFromBox(box)
        if page_num != -1:
            self.boxeditor_notebook.set_current_page(page_num)
        else:
            num_boxes = self.boxeditor_notebook.get_n_pages()
            self.addBoxEditor(box)
            self.boxeditor_notebook.set_current_page(num_boxes)
        self.updateMainWindow()

    def deselectedBoxCb(self, widget, box):
        self.updateMainWindow()

    def updatedBox(self, widget, box):
        for editor in self.editor_list:
            if editor.box == box:
                editor.update(box)

    def updatedBoxBounds(self, widget, box):
        for editor in self.editor_list:
            if editor.box == box:
                editor.updateBounds(box)

    def removedBox(self, widget, box):
        self.updateMainWindow()
        for i in xrange(len(self.editor_list)):
            editor = self.editor_list[i]
            if editor.box == box:
                page_num = self.boxeditor_notebook.page_num(editor.box_editor)
                self.boxeditor_notebook.remove_page(page_num)
                del self.editor_list[i]
                return True
        return False

    def __getPageNumFromBox(self, box):
        editor = self.__getEditorFromBox(box)
        if editor:
            return self.boxeditor_notebook.page_num(editor.box_editor)
        return -1

    def __getEditorFromBox(self, box):
        for editor in self.editor_list:
            if editor.box == box:
                return editor
        return None

    def applyTextColors(self):
        self.selectable_boxes_area.fill_color_rgba = self.text_box_fill_color
        self.selectable_boxes_area.stroke_color_rgba = self.box_stroke_color

    def applyImageColors(self):
        self.selectable_boxes_area.fill_color_rgba = self.image_box_fill_color
        self.selectable_boxes_area.stroke_color_rgba = self.box_stroke_color

    def addNewEditorsToAllBoxes(self):
        self.editor_list = []
        boxes = self.selectable_boxes_area.getAllAreas()
        for box in boxes:
            self.addBoxEditor(box)

    def performOcrForAllEditors(self, engine = None):
        self.performOcrForEditors(self.editor_list, engine)

    def performOcrForSelectedBoxes(self, engine = None):
        selected_boxes = self.selectable_boxes_area.getSelectedAreas()
        self.performOcrForEditors([self.__getEditorFromBox(box) \
                                   for box in selected_boxes],
                                  engine)

    def performOcrForEditors(self, editors_list, engine = None):
        for editor in editors_list:
            if editor == None:
                continue
            editor.performOcr(engine)
            editor.performClassification(engine)
            if editor.box_editor.getType() == IMAGE_TYPE:
                editor.box_editor.setText('')
        self.updateMainWindow()

    def __getAllDataBoxes(self):
        boxes = []
        for editor in self.editor_list:
            editor.setDataBox()
            data_box = editor.data_box
            boxes.append((data_box.y, data_box))
            boxes.sort()
        boxes_sorted = []
        for y, box in boxes:
            boxes_sorted.append(box)
        boxes = boxes_sorted
        return boxes

    def getPageData(self):
        self.page.data_boxes = self.__getAllDataBoxes()
        return self.page

    def updatePageData(self, page_data):
        self.page = page_data
        for data_box in self.page.data_boxes:
            self.addDataBox(data_box)

    def addDataBox(self, data_box):
        dimensions = (int(data_box.x), int(data_box.y), int(data_box.width), int(data_box.height))
        box = self.selectable_boxes_area.addArea(dimensions)
        editor = self.addBoxEditor(box)
        editor.box = box
        editor.updateDataBox(data_box)

    def updateBackgroundImage(self, image_path):
        self.path_to_image = image_path
        if not os.path.exists(self.path_to_image):
            return
        try:
            self.image_pixbuf = gtk.gdk.pixbuf_new_from_file(self.path_to_image)
        except Exception, exception:
            debug(exception.message)
            return
        self.selectable_boxes_area.setBackgroundImage(self.path_to_image)

    def updateBoxesColors(self):
        for editor in self.editor_list:
            editor.updateBoxColor()

    def zoomFitCb(self, widget, data):
        self.zoomFit()
        widget.disconnect_by_func(self.zoomFitCb)

    def zoomFit(self):
        parent = self.selectable_boxes_area.get_parent()
        parent_height, parent_width = parent.allocation.height, parent.allocation.width
        image_height, image_width = self.selectable_boxes_area.getImageSize()
        changed = False
        if image_height > parent_height:
            image_height = parent_height / image_height
            changed = True
        if image_width > parent_width:
            image_width = parent_width / image_width
            changed = True
        if changed:
            self.selectable_boxes_area.zoom(min(image_height, image_width), False)

    def updateMainWindow(self):
        has_selected_areas = self.selectable_boxes_area.getSelectedAreas()
        has_boxes = self.selectable_boxes_area.getAllAreas()
        self.main_window.setHasSelectedBoxes(bool(has_selected_areas))
        self.main_window.setHasContentBoxes(bool(has_boxes))

class ImageReviewer_Controler:

    def __init__(self, main_window, images_dict, source_images_selector_widget,
                 ocr_engines, configuration_manager,
                 selection_changed_signal = 'selection-changed'):
        self.main_window = main_window
        self.notebook = self.main_window.notebook
        self.image_reviewer_dict = {}
        self.source_images_selector_widget = source_images_selector_widget
        self.ocr_engines = ocr_engines
        self.configuration_manager = configuration_manager
        self.tripple_statusbar = self.main_window.tripple_statusbar
        for key, image in images_dict.items():
            self.addImage(key, image)
        self.source_images_selector_widget.connect(selection_changed_signal, self.selectImageReviewer)

    def addImage(self, pixbuf, image):
        image_reviewer = ImageReviewer(self.main_window, image, self.ocr_engines)
        image_reviewer.selectable_boxes_area.connect('changed_zoom', self.__setZoomStatus)
        image_reviewer.setTextFillColor(self.configuration_manager.text_fill)
        image_reviewer.setBoxesStrokeColor(self.configuration_manager.boxes_stroke)
        image_reviewer.setImageFillColor(self.configuration_manager.image_fill)
        self.image_reviewer_dict[pixbuf] = image_reviewer
        self.addImageReviewer(image_reviewer.reviewer_area)
        return image_reviewer

    def addImageFromPath(self, image_path):
        pixbuf, image, iter = self.source_images_selector_widget.source_images_selector.addImage(image_path)
        return self.addImage(pixbuf, image)

    def addImageReviewer(self, image_reviewer_widget):
        self.notebook.append_page(image_reviewer_widget, None)

    def selectImageReviewer(self, widget):
        pixbuf = self.source_images_selector_widget.getSelectedPixbuf()
        if pixbuf != None:
            reviewer = self.image_reviewer_dict[pixbuf]
            self.notebook.set_current_page(self.notebook.page_num(reviewer.reviewer_area))
            self.__setZoomStatus(None, reviewer.selectable_boxes_area.get_scale())
            self.tripple_statusbar.center_statusbar.insert((_('Page size') + ': %.2f x %.2f') % (reviewer.getPageData().width, reviewer.getPageData().height))
            self.tripple_statusbar.right_statusbar.insert((_('Resolution') + ': %i x %i') % (reviewer.getPageData().resolution[0], reviewer.getPageData().resolution[1]))
            reviewer.updateMainWindow()

    def __setZoomStatus(self, widget, zoom):
        self.tripple_statusbar.left_statusbar.insert(_('Zoom') + ': ' + str(int(zoom * 100)) + '%')

    def recognizeSelectedAreas(self, widget):
        image_reviewer = self.__getCurrentReviewer()
        image_reviewer.performOcrForSelectedBoxes(self.configuration_manager.favorite_engine)

    def recognizeCurrentPage(self):
        image_reviewer = self.__getCurrentReviewer()
        image_reviewer.selectable_boxes_area.clearAreas()
        image_reviewer.applyTextColors()
        dialog = QueuedEventsProgressDialog(self.main_window.window)
        item = AsyncItem(self.__performRecognitionForReviewer,
                         (image_reviewer,),
                         self.__performRecognitionForReviewerFinishedCb,
                         (dialog, image_reviewer,))
        info = (_('Recognizing Document'), _('Please wait…'))
        dialog.setItemsList([(info, item)])
        dialog.run()

    def __performRecognitionForReviewer(self, image_reviewer):
        window_size = self.configuration_manager.window_size
        if window_size == 'auto':
            window_size = None
        else:
            window_size = float(window_size)
        improve_column_detection = \
            self.configuration_manager.improve_column_detection
        column_min_width = self.configuration_manager.column_min_width
        if column_min_width == 'auto':
            column_min_width = None
        clean_text = self.configuration_manager.clean_text

        layout_analysis = LayoutAnalysis(self.__getConfiguredOcrEngine(),
                                         window_size,
                                         improve_column_detection,
                                         column_min_width,
                                         clean_text)
        return layout_analysis.recognize(image_reviewer.path_to_image,
                                         image_reviewer.page.resolution[1])

    def __getConfiguredOcrEngine(self):
        for engine, path in self.ocr_engines:
            if engine.name == self.configuration_manager.favorite_engine:
                return engine
        return None

    def __performRecognitionForReviewerFinishedCb(self, dialog, image_reviewer,
                                                  data_boxes, error):
        for data_box in data_boxes:
            image_reviewer.addDataBox(data_box)
        dialog.cancel()

    def setDataBox(self, widget):
        image_reviewer = self.__getCurrentReviewer()
        document_generator = OdtGenerator()
        page_data = image_reviewer.getPageData()
        document_generator.addPage(page_data)
        document_generator.save()

    def exportPagesToHtml(self, pixbufs_sorted = []):
        image_reviewers = self.__askForNumberOfPages(_('Export to HTML'), pixbufs_sorted)
        if not image_reviewers:
            return
        file_name = self.__askForFileName()
        if file_name:
            if os.path.exists(file_name):
                os.remove(file_name)
            document_generator = HtmlGenerator(file_name)
            for image_reviewer in image_reviewers:
                document_generator.addPage(image_reviewer.getPageData())
            document_generator.save()


    def exportPagesToOdt(self, pixbufs_sorted = []):
        image_reviewers = self.__askForNumberOfPages(_('Export to ODT'), pixbufs_sorted)
        if not image_reviewers:
            return
        file_name = self.__askForFileName()
        if file_name:
            document_generator = OdtGenerator(file_name)
            for image_reviewer in image_reviewers:
                document_generator.addPage(image_reviewer.getPageData())
            document_generator.save()

    def saveProjectAs(self):
        return self.__askForFileName(extension = '.ocrf')

    def saveProject(self, project_name):
        if not project_name.endswith('.ocrf'):
            project_name += '.ocrf'
        pages_data = self.getPagesData(self.getPixbufsSorted())
        project_saver = ProjectSaver(pages_data, self.configuration_manager.temporary_dir)
        project_saver.serialize(project_name)

    def openProject(self, clear_current = True):
        open_dialog = FileDialog('open', file_filters = [(_('OCRFeeder Projects'), [], ['*.ocrf'])])
        response = open_dialog.run()
        project_file = None
        if response == gtk.RESPONSE_OK:
            project_file = open_dialog.get_filename()
            project_loader = ProjectLoader(project_file)
            pages = project_loader.loadConfiguration()
            if pages and clear_current:
                self.clear()
            for page in pages:
                image_reviewer = self.addImageFromPath(page.image_path)
                image_reviewer.updatePageData(page)
        open_dialog.destroy()
        return project_file

    def __askForNumberOfPages(self, title, pixbufs_sorted):
        export_dialog = PagesToExportDialog(title)
        image_reviewers = self.getImageReviewers(pixbufs_sorted)
        # When there's only one document loaded or none,
        # we don't ask for the number of pages to export
        if len(image_reviewers) < 2:
            return image_reviewers
        response = export_dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            if export_dialog.current_page_button.get_active():
                image_reviewers = [self.__getCurrentReviewer()]
            export_dialog.destroy()
            return image_reviewers
        else:
            export_dialog.destroy()
            return None

    def getImageReviewers(self, pixbufs_sorted):
        image_reviewers = []
        if not pixbufs_sorted:
            for key, image_reviewer in self.image_reviewer_dict.items():
                image_reviewers.append(image_reviewer)
        else:
            for pixbuf in pixbufs_sorted:
                image_reviewers.append(self.image_reviewer_dict[pixbuf])
        return image_reviewers

    def getPagesData(self, pixbufs_sorted):
        image_reviewers = self.getImageReviewers(pixbufs_sorted)
        return [reviewer.getPageData() for reviewer in image_reviewers]

    def __askForFileName(self, extension = ''):
        save_dialog = FileDialog('save')
        response = save_dialog.run()
        if response == gtk.RESPONSE_OK:
            file_name = save_dialog.get_filename()
            if extension:
                if not file_name.endswith(extension):
                    file_name += extension
            if os.path.isfile(file_name):
                confirm_overwrite = gtk.MessageDialog(type = gtk.MESSAGE_QUESTION)
                message = _('<b>A file named "%(name)s" already exists. Do you want '
                            'to replace it?</b>\n\nThe file exists in "%(dir)s". '
                            'Replacing it will overwrite its contents.' %
                            {'name': os.path.basename(file_name),
                             'dir': os.path.dirname(file_name)})
                confirm_overwrite.set_markup(message)
                confirm_overwrite.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
                confirm_overwrite.add_button(_('Replace'), gtk.RESPONSE_OK)
                if confirm_overwrite.run() != gtk.RESPONSE_OK:
                    file_name = None
                confirm_overwrite.destroy()
            save_dialog.destroy()
            return file_name
        save_dialog.destroy()
        return None

    def choosePageSize(self):
        current_reviewer = self.__getCurrentReviewer()
        current_page = current_reviewer.page
        page_size_dialog = PageSizeDialog((current_page.width, current_page.height))
        response = page_size_dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            size = page_size_dialog.getSize()
            if page_size_dialog.all_pages_radio.get_active():
                for key, reviewer in self.image_reviewer_dict.items():
                    reviewer.page.setSize(size)
            else:
                current_reviewer.page.setSize(size)
            debug('Page size: ', size)
        page_size_dialog.destroy()

    def __getCurrentReviewer(self):
        current_reviewer_area = self.notebook.get_nth_page(self.notebook.get_current_page())
        image_reviewer = None
        for key, reviewer in self.image_reviewer_dict.items():
            if reviewer.reviewer_area == current_reviewer_area:
                image_reviewer = reviewer
                return image_reviewer

    def deleteCurrentPage(self):
        current_reviewer = self.__getCurrentReviewer()
        for pixbuf, image_reviewer in self.image_reviewer_dict.items():
            if image_reviewer == current_reviewer:
                del self.image_reviewer_dict[pixbuf]
                self.notebook.remove_page(self.notebook.get_current_page())
                return True

    def unpaperTool(self):
        current_reviewer = self.__getCurrentReviewer()
        unpaper_dialog = UnpaperDialog(current_reviewer, self.configuration_manager.unpaper, self.configuration_manager.temporary_dir)
        if unpaper_dialog.run() == gtk.RESPONSE_ACCEPT:
            unpapered_image = unpaper_dialog.getUnpaperedImage()
            current_reviewer.updateBackgroundImage(unpapered_image)
            unpaper_dialog.destroy()
        else:
            unpaper_dialog.destroy()

    def clear(self):
        for pixbuf in self.image_reviewer_dict.keys():
            del self.image_reviewer_dict[pixbuf]
            self.notebook.remove_page(self.notebook.get_current_page())
        self.source_images_selector_widget.clear()
        self.tripple_statusbar.clear()

    def getPixbufsSorted(self):
        return self.source_images_selector_widget.source_images_selector.getPixbufsSorted()

    def updateFromConfiguration(self):
        for reviewer in self.image_reviewer_dict.values():
            reviewer.setTextFillColor(self.configuration_manager.text_fill)
            reviewer.setBoxesStrokeColor(self.configuration_manager.boxes_stroke)
            reviewer.setImageFillColor(self.configuration_manager.image_fill)
            reviewer.updateBoxesColors()

    def zoomIn(self, zoom_value = 0.05):
        current_reviewer = self.__getCurrentReviewer()
        current_reviewer.selectable_boxes_area.zoom(zoom_value)

    def zoomOut(self, zoom_value = -0.05):
        current_reviewer = self.__getCurrentReviewer()
        current_reviewer.selectable_boxes_area.zoom(-abs(zoom_value))

    def zoomFit(self):
        current_reviewer = self.__getCurrentReviewer()
        current_reviewer.zoomFit()

    def resetZoom(self):
        current_reviewer = self.__getCurrentReviewer()
        current_reviewer.selectable_boxes_area.zoom(1, False)

    def selectPreviousArea(self, widget):
        current_reviewer = self.__getCurrentReviewer()
        current_reviewer.selectable_boxes_area.selectPreviousArea()

    def selectNextArea(self, widget):
        current_reviewer = self.__getCurrentReviewer()
        current_reviewer.selectable_boxes_area.selectNextArea()

    def selectAllAreas(self, widget):
        current_reviewer = self.__getCurrentReviewer()
        current_reviewer.selectable_boxes_area.selectAllAreas()

    def deleteSelectedAreas(self, widget):
        current_reviewer = self.__getCurrentReviewer()
        current_reviewer.selectable_boxes_area.deleteSelectedAreas()

class Editor:

    def __init__(self, box, pixbuf, ocr_engines, reviewer):
        self.pixbuf = pixbuf
        self.data_box = DataBox()
        self.box_editor = BoxEditor(pixbuf.get_width(), pixbuf.get_height())
        self.reviewer = reviewer
        self.ocr_engines = ocr_engines
        self.updateOcrEngines(self.ocr_engines)
        self.box_editor.x_spin_button.connect('value-changed', self.__updateBoxX)
        self.box_editor.y_spin_button.connect('value-changed', self.__updateBoxY)
        self.box_editor.width_spin_button.connect('value-changed', self.__updateBoxWidth)
        self.box_editor.height_spin_button.connect('value-changed', self.__updateBoxHeight)
        self.box_editor.make_text_button.connect('toggled', self.__pressedTextContextButton)
        self.box_editor.make_image_button.connect('toggled', self.__pressedImageContextButton)
        self.box_editor.perform_ocr_button.connect('clicked', self.__pressedPerformOcrButton)
        self.box_editor.detect_angle_button.connect('clicked', self.__pressedAngleDetectionButton)
        self.box_editor.font_button.connect('font-set', self.__setDataBoxFont)
        self.box_editor.align_left_button.connect('toggled', self.__setDataBoxAlign, ALIGN_LEFT)
        self.box_editor.align_right_button.connect('toggled', self.__setDataBoxAlign, ALIGN_RIGHT)
        self.box_editor.align_center_button.connect('toggled', self.__setDataBoxAlign, ALIGN_CENTER)
        self.box_editor.align_fill_button.connect('toggled', self.__setDataBoxAlign, ALIGN_FILL)
        self.box_editor.letter_spacing_spin.connect('value-changed', self.__setDataBoxLetterSpacing)
        self.box_editor.line_spacing_spin.connect('value-changed', self.__setDataBoxLineSpacing)
        self.__connectDataBoxSignals()
        self.update(box)

    def __updateBoxX(self, spin_button):
        self.box.set_property('x', self.box_editor.getX())
        if spin_button.is_focus():
            self.update(self.box)

    def __updateBoxY(self, spin_button):
        self.box.set_property('y', self.box_editor.getY())
        if spin_button.is_focus():
            self.update(self.box)

    def __updateBoxWidth(self, spin_button):
        self.box.set_property('width', self.box_editor.getWidth())
        if spin_button.is_focus():
            self.update(self.box)

    def __updateBoxHeight(self, spin_button):
        self.box.set_property('height', self.box_editor.getHeight())
        if spin_button.is_focus():
            self.update(self.box)

    def __updateEditorX(self, widget, new_x):
        self.box_editor.setXRange()
        self.box_editor.setX(new_x)

    def __updateEditorY(self, widget, new_y):
        self.box_editor.setY(new_y)

    def __updateEditorWidth(self, widget, new_width):
        self.box_editor.setWidth(new_width)

    def __updateEditorHeight(self, widget, new_height):
        self.box_editor.setHeight(new_height)

    def __updateEditorImage(self, widget, new_image):
        self.box_editor.displayImage(new_image)

    def __updateBoxColor(self, widget, type):
        self.updateBoxColor(type)

    def updateBoxColor(self, type = None):
        type = type or self.data_box.getType()
        stroke_color = graphics.rgbaToInteger(self.reviewer.box_stroke_color)
        fill_color = graphics.rgbaToInteger(self.reviewer.image_box_fill_color)
        if type == TEXT_TYPE:
            fill_color = graphics.rgbaToInteger(self.reviewer.text_box_fill_color)
        self.box.set_property('fill-color-rgba', fill_color)
        self.box.set_property('stroke-color-rgba', stroke_color)

    def __setDataBoxFont(self, font_button = None):
        font_button = font_button or self.box_editor.font_button
        font_description = FontDescription(font_button.get_font_name())
        self.data_box.setFontFace(font_description.get_family())
        self.data_box.setFontSize(font_description.get_size() / SCALE)
        self.data_box.setFontStyle(font_description.get_style())
        self.data_box.setFontWeight(font_description.get_weight())

    def __setDataBoxAlign(self, align_button, align_option):
        if align_button.get_active():
            self.data_box.setTextAlign(align_option)

    def __setDataBoxLetterSpacing(self, letter_spacing_button = None):
        letter_spacing_button = letter_spacing_button or self.box_editor.letter_spacing_spin
        self.data_box.setLetterSpacing(letter_spacing_button.get_value())

    def __setDataBoxLineSpacing(self, line_spacing_button = None):
        line_spacing_button = line_spacing_button or self.box_editor.line_spacing_spin
        self.data_box.setLineSpacing(line_spacing_button.get_value())

    def update(self, box):
        self.box = box
        x, y, width, height = self.updateBounds(box)
        pixbuf_width = self.pixbuf.get_width()
        pixbuf_height = self.pixbuf.get_height()
        sub_pixbuf = self.pixbuf.subpixbuf(x, y, min(width, pixbuf_width), min(height, pixbuf_height))
        self.data_box.setImage(sub_pixbuf)

    def updateBounds(self, box):
        self.box = box
        x, y, width, height = int(self.box.props.x), int(self.box.props.y), \
                            int(self.box.props.width), int(self.box.props.height)
        self.data_box.setX(x)
        self.data_box.setY(y)
        self.data_box.setWidth(width)
        self.data_box.setHeight(height)
        return (x, y, width, height)

    def updateOcrEngines(self, engines_list):
        engines_names = [engine.name for engine, path in engines_list]
        self.box_editor.setOcrEngines(engines_names)

    def __pressedImageContextButton(self, toggle_button):
        self.data_box.setType(IMAGE_TYPE)
        self.box_editor.setOcrPropertiesSensibility(False)

    def __pressedTextContextButton(self, toggle_button):
        self.data_box.setType(TEXT_TYPE)
        self.box_editor.setOcrPropertiesSensibility(True)

    def __pressedPerformOcrButton(self, button):
        self.performOcr()

    def performOcr(self, engine_name = None):
        selected_engine_index = self.box_editor.getSelectedOcrEngine()
        if engine_name:
            for i in xrange(len(self.ocr_engines)):
                if self.ocr_engines[i][0].name == engine_name:
                    selected_engine_index = i
                    break
        self.box_editor.selectOcrEngine(selected_engine_index)
        image = graphics.convertPixbufToImage(self.box_editor.getImage())
        angle = self.box_editor.getAngle()
        if angle:
            image = graphics.getImageRotated(image, angle)
        engine = None
        if selected_engine_index != -1:
            engine = self.ocr_engines[selected_engine_index][0]
        layout_analysis = LayoutAnalysis(engine)
        text = layout_analysis.readImage(image)
        self.box_editor.setText(text)
        debug('Finished reading')
        text_size = layout_analysis.getTextSizeFromImage(image,
                                               self.reviewer.page.resolution[1])
        if text_size:
            self.box_editor.setFontSize(text_size)

    def performClassification(self, engine_name = None):
        selected_engine_index = self.box_editor.getSelectedOcrEngine()
        if engine_name:
            for i in xrange(len(self.ocr_engines)):
                if self.ocr_engines[i][0].name == engine_name:
                    selected_engine_index = i
                    break
        if selected_engine_index != None:
            engine = self.ocr_engines[selected_engine_index][0]
            type = engine.classify(self.box_editor.getText())
            self.box_editor.setType(type)

    def __pressedAngleDetectionButton(self, widget):
        image = graphics.convertPixbufToImage(self.box_editor.getImage())
        angle = graphics.getHorizontalAngleForText(image)
        debug('ANGLE: ', angle)
        self.box_editor.setAngle(angle)

    def setDataBox(self):
        text = self.box_editor.getText()
        self.data_box.setText(text)
        angle = self.box_editor.getAngle()
        self.data_box.setAngle(angle)
        self.__setDataBoxFont()
        self.__setDataBoxLetterSpacing()
        self.__setDataBoxLineSpacing()


    def updateDataBox(self, data_box):
        self.data_box = data_box
        self.box_editor.setX(self.data_box.x)
        self.box_editor.setY(self.data_box.y)
        self.box_editor.setWidth(self.data_box.width)
        self.box_editor.setHeight(self.data_box.height)
        self.box_editor.setType(self.data_box.type)
        self.box_editor.setText(self.data_box.text)
        self.box_editor.setFontSize(self.data_box.text_data.size)
        self.__connectDataBoxSignals()
        self.__updateBoxColor(None, self.data_box.type)

    def __connectDataBoxSignals(self):
        self.data_box.connect('changed_x', self.__updateEditorX)
        self.data_box.connect('changed_y', self.__updateEditorY)
        self.data_box.connect('changed_width', self.__updateEditorWidth)
        self.data_box.connect('changed_height', self.__updateEditorHeight)
        self.data_box.connect('changed_image', self.__updateEditorImage)
        self.data_box.connect('changed_type', self.__updateBoxColor)
