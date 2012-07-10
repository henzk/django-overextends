from __future__ import absolute_import
from django.template.loaders import filesystem
from django.template import loader
from django.template import TemplateDoesNotExist
from os.path import dirname
from .templatetags.overextends_tags import SuperimposeNode

TEMPLATE_SEARCHPATH = None
TEMPLATE_SEARCHPATH_INDEX = None

def get_template_searchpath():
    global TEMPLATE_SEARCHPATH
    global TEMPLATE_SEARCHPATH_INDEX
    from django.template.loaders.app_directories import app_template_dirs
    from django.conf import settings
    if TEMPLATE_SEARCHPATH is None:
        TEMPLATE_SEARCHPATH_INDEX = dict()
        TEMPLATE_SEARCHPATH = list(settings.TEMPLATE_DIRS) + list(app_template_dirs)
        for index, elem in enumerate(TEMPLATE_SEARCHPATH):
            TEMPLATE_SEARCHPATH_INDEX[elem] = index
    return TEMPLATE_SEARCHPATH

class SuperimposingLoader(filesystem.Loader):
    '''
    Custom template loader needed for the superimpose template tag
    '''
    is_usable=True
    supports_superimposition=True

    def load_template(self, template_name, template_dirs=None, start_index=0):
        '''
        load template from the filesystem
        settings.TEMPLATE_DIRS and app template directories are searched for
        a matching template. start_index is the index in searchpath where
        the search begins. All directories before index are skipped.
        template_dirs must be None or an exception will be raised.

        adapted from django.template.base.BaseLoader
        '''
        if template_dirs is not None:
            raise Exception(
                'template_dirs kwarg not supported by this loader'
            )
        dirs = get_template_searchpath()[start_index:]
        source, display_name = self.load_template_source(
            template_name,
            template_dirs=dirs
        )
        origin = loader.make_origin(
            display_name,
            self.load_template_source,
            template_name,
            template_dirs
        )
        try:
            template = loader.get_template_from_string(source, origin, template_name)
            template_index = TEMPLATE_SEARCHPATH_INDEX[
                dirname(display_name)]
            first_node = template.nodelist[0]
            if isinstance(first_node, SuperimposeNode):
                #evil: inject template index and name
                first_node.template_index = template_index
                first_node.template_name = template_name
            return template, None
        except TemplateDoesNotExist:
            # If compiling the template we found raises TemplateDoesNotExist, back off to
            # returning the source and display name for the template we were asked to load.
            # This allows for correct identification (later) of the actual template that does
            # not exist.
            return source, display_name
