
from django import template
from django.template import Template, TemplateSyntaxError, TemplateDoesNotExist
from django.template.loader_tags import ExtendsNode
from django.template.loader import find_template_loader, find_template


register = template.Library()


class OverExtendsNode(ExtendsNode):
    """
    Allows the template ``foo/bar.html`` to extend ``foo/bar.html``,
    given that there is another version of it that can be loaded. This
    allows templates to be created in a project that extend their app
    template counterparts, or even app templates that extend other app
    templates with the same relative name/path.

    We use our own version of ``find_template``, that uses an explict
    list of template directories to search for the template, based on
    the directories that the known template loaders
    (``app_directories`` and ``filesystem``) use. This list gets stored
    in the template context, and each time a template is found, its
    absolute path gets removed from the list, so that subsequent
    searches for the same relative name/path can find parent templates
    in other directories, which allows circular inheritance to occur.

    Django's ``app_directories``, ``filesystem``, and ``cached``
    loaders are supported. The ``eggs`` loader, and any loader that
    implements ``load_template_source`` with a source string returned,
    should also theoretically work.
    """

    def find_template(self, name, context):
        """
        Replacement for Django's ``find_template`` that uses the current
        template context to keep track of which template directories it
        has used when finding a template. This allows multiple templates
        with the same relative name/path to be discovered, so that
        circular template inheritance can occur.
        """

        # These imports want settings, which aren't available when this
        # module is imported to ``add_to_builtins``, so do them here.
        from django.template.loaders.app_directories import app_template_dirs
        from django.conf import settings

        # Store a dictionary in the template context mapping template
        # names to the lists of template directories available to
        # search for that template. Each time a template is loaded, its
        # origin directory is removed from its directories list.
        context_name = "OVEREXTENDS_DIRS"
        if context_name not in context:
            context[context_name] = {}
        if name not in context[context_name]:
            all_dirs = list(settings.TEMPLATE_DIRS + app_template_dirs)
            context[context_name][name] = all_dirs

        # Build a list of template loaders to use. For loaders that wrap
        # other loaders like the ``cached`` template loader, unwind its
        # internal loaders and add those instead.
        loaders = []
        for loader_name in settings.TEMPLATE_LOADERS:
            loader = find_template_loader(loader_name)
            loaders.extend(getattr(loader, "loaders", [loader]))

        # Go through the loaders and try to find the template. When
        # found, removed its absolute path from the context dict so
        # that it won't be used again when the same relative name/path
        # is requested.
        for loader in loaders:
            dirs = context[context_name][name]
            try:
                source, path = loader.load_template_source(name, dirs)
            except TemplateDoesNotExist:
                pass
            else:
                context[context_name][name].remove(path[:-len(name) - 1])
                return Template(source)
        raise TemplateDoesNotExist(name)

    def get_parent(self, context):
        """
        Load the parent template using our own ``find_template``, which
        will cause its absolute path to not be used again. Then peek at
        the first node, and if its parent arg is the same as the
        current parent arg, we know circular inheritance is going to
        occur, in which case we try and find the template again, with
        the absolute directory removed from the search list.
        """
        parent = self.parent_name.resolve(context)
        # If parent is a template object, just return it.
        if hasattr(parent, "render"):
            return parent
        template = self.find_template(parent, context)
        if (isinstance(template.nodelist[0], ExtendsNode) and
            template.nodelist[0].parent_name.resolve(context) == parent):
            return self.find_template(parent, context)
        return template


@register.tag
def overextends(parser, token):
    """
    Extended version of Django's ``extends`` tag that allows circular
    inheritance to occur, eg a template can both be overridden and
    extended at once.
    """
    bits = token.split_contents()
    if len(bits) != 2:
        raise TemplateSyntaxError("'%s' takes one argument" % bits[0])
    parent_name = parser.compile_filter(bits[1])
    nodelist = parser.parse()
    if nodelist.get_nodes_by_type(ExtendsNode):
        raise TemplateSyntaxError("'%s' cannot appear more than once "
                                  "in the same template" % bits[0])
    return OverExtendsNode(nodelist, parent_name, None)


_LOADER = None

def _get_loader():
    global _LOADER
    if _LOADER is None:
        from django.conf import settings
        loaders = []
        for loader_name in settings.TEMPLATE_LOADERS:
            loader = find_template_loader(loader_name)
            loaders.extend(getattr(loader, "loaders", [loader]))
        if len(loaders) != 1:
            raise Exception(
                'TEMPLATE_LOADERS may only contain a single loader!'
            )
        if not hasattr(loaders[0], 'supports_superimposition'):
            raise Exception(
                'The loader in TEMPLATE_LOADERS '
                'does not support superimposition'
            )
        _LOADER = loaders[0]
    return _LOADER

class SuperimposeNode(ExtendsNode):
    template_index = -1
    template_name = ''
    parent = None

    def find_template(self, name):
        loader = _get_loader()
        template, display_name = loader.load_template(name, start_index=self.template_index + 1)
        if display_name is None:
            return template
        else:
            raise Exception(
                'FIXME! TemplateDoesNotExist caught in load_template'
            )

    def get_parent(self, context):
        if not self.parent:
            self.parent = self.find_template(self.template_name)
        return self.parent

@register.tag
def superimpose(parser, token):
    bits = token.split_contents()
    if len(bits) != 1:
        raise TemplateSyntaxError("'%s' takes no arguments" % bits[0])
    nodelist = parser.parse()
    if nodelist.get_nodes_by_type(ExtendsNode):
        raise TemplateSyntaxError("'%s' cannot appear more than once "
                                  "in the same template" % bits[0])
    return SuperimposeNode(nodelist, None, None)
