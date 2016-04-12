import re

from ucca import layer0
from ucca.layer1 import EdgeTags

FEATURE_ELEMENT_PATTERN = re.compile("([sba])(\d)([lrup]*)([wtepqxyPCIR]*)")
FEATURE_TEMPLATE_PATTERN = re.compile("^(%s)+$" % FEATURE_ELEMENT_PATTERN.pattern)


class FeatureTemplate(object):
    """
    A feature template in parsed form, ready to be used for value calculation
    """
    def __init__(self, name, elements):
        """
        :param name: name of the feature in the short-hand form, to be used for the dictionary
        :param elements: collection of FeatureElement objects that represent the actual feature
        """
        self.name = name
        self.elements = elements


class FeatureTemplateElement(object):
    """
    One element in the values of a feature, e.g. from one node
    """
    def __init__(self, source, index, children, properties):
        """
        :param source: where to take the data from:
                           s: stack nodes
                           b: buffer nodes
                           a: past actions
        :param index: non-negative integer, the index of the element in the stack, buffer or list
                           of past actions (in the case of stack and actions, indexing from the end)
        :param children: string in [lrup]*, to select a descendant of the node instead:
                           l: leftmost child
                           r: rightmost child
                           u: only child, if there is just one
                           p: parent
        :param properties: the actual values to choose, if available (else omit feature), out of:
                           w: node text / action type
                           t: node POS tag
                           e: tag of first incoming edge / action tag
                           p: unique separator punctuation between nodes
                           q: count of any separator punctuation between nodes
                           x: gap type
                           y: sum of gap lengths
                           P: number of parents
                           C: number of children
                           I: number of implicit children
                           R: number of remote children
                           If empty, the value will be 1 if there is an edge from this node to the
                           next one in the template, or 0 otherwise. Also, if the next node comes
                           with the "e" property, then the edge with this node will be considered.
        """
        self.source = source
        self.index = int(index)
        self.children = children
        self.properties = properties


class FeatureExtractor(object):
    """
    Object to extract features from the parser state to be used in action classification
    """
    def __init__(self, feature_templates):
        assert all(FEATURE_TEMPLATE_PATTERN.match(f) for f in feature_templates), \
            "Features do not match pattern: " + ", ".join(
                f for f in feature_templates if not FEATURE_TEMPLATE_PATTERN.match(f))
        # convert the list of features textual descriptions to the actual fields
        self.feature_templates = [FeatureTemplate(
            feature_name, tuple(FeatureTemplateElement(*m.group(1, 2, 3, 4))
                                for m in re.finditer(FEATURE_ELEMENT_PATTERN, feature_name)))
                                  for feature_name in feature_templates]

    def extract_features(self, state):
        """
        Calculate feature values according to current state
        :param state: current state of the parser
        """
        raise NotImplementedError()

    @staticmethod
    def calc_feature(feature_template, state):
        values = []
        prev_node = None
        for element in feature_template.elements:
            if element.source == "s":
                if len(state.stack) <= element.index:
                    return None
                node = state.stack[-1 - element.index]
            elif element.source == "b":
                if len(state.buffer) <= element.index:
                    return None
                node = state.buffer[element.index]
            else:  # source == "a"
                if len(state.actions) <= element.index:
                    return None
                node = state.actions[-1 - element.index]
            for child in element.children:
                if child == "p":
                    if node.parents:
                        node = node.parents[0]
                    else:
                        return None
                elif not node.children:
                    return None
                elif len(node.children) == 1:
                    if child == "u":
                        node = node.children[0]
                elif child == "l":
                    node = node.children[0]
                elif child == "r":
                    node = node.children[-1]
                else:  # child == "u" and len(node.children) > 1
                    return None
            if not element.properties:
                if prev_node is not None:
                    values.append("1" if prev_node in node.parents else "0")
                prev_node = node
            else:
                prev_node = None
                for p in element.properties:
                    try:
                        if element.source == "a":
                            v = FeatureExtractor.get_action_prop(node, p)
                        elif p in "pq":
                            v = FeatureExtractor.get_separator_prop(
                                state.stack[-1:-3:-1], state.terminals, p)
                        else:
                            v = FeatureExtractor.get_prop(node, p, prev_node)
                    except (AttributeError, StopIteration):
                        v = None
                    if v is None:
                        return None
                    values.append(str(v))
        return values

    @staticmethod
    def get_prop(node, p, prev_node=None):
        if p == "w":
            return FeatureExtractor.get_head_terminal(node).text
        if p == "t":
            return FeatureExtractor.get_head_terminal(node).pos_tag
        if p == "e":
            return next(e.tag for e in node.incoming
                        if prev_node is None or e.parent == prev_node)
        if p == "x":
            return FeatureExtractor.gap_type(node)
        if p == "y":
            return FeatureExtractor.gap_length_sum(node)
        if p == "P":
            return len(node.incoming)
        if p == "C":
            return len(node.outgoing)
        if p == "I":
            return len([n for n in node.children if n.implicit])
        if p == "R":
            return len([e for e in node.outgoing if e.remote])
        raise Exception("Unknown node property: " + p)

    @staticmethod
    def get_action_prop(action, p):
        if p == "w":
            return action.type
        if p == "e":
            return action.tag
        raise Exception("Unknown action property: " + p)

    @staticmethod
    def get_separator_prop(nodes, terminals, p):
        if len(nodes) < 2:
            return None
        t0, t1 = sorted([FeatureExtractor.get_head_terminal(node) for node in nodes],
                        key=lambda t: t.index)
        punctuation = [terminal for terminal in terminals[t0.index + 1:t1.index]
                       if terminal.tag == layer0.NodeTags.Punct]
        if p == "p" and len(punctuation) == 1:
            return punctuation[0].text
        if p == "q":
            return len(punctuation)
        return None

    EDGE_PRIORITY = {tag: i for i, tag in enumerate((
        EdgeTags.Center,
        EdgeTags.Connector,
        EdgeTags.ParallelScene,
        EdgeTags.Process,
        EdgeTags.State,
        EdgeTags.Participant,
        EdgeTags.Adverbial,
        EdgeTags.Time,
        EdgeTags.Elaborator,
        EdgeTags.Relator,
        EdgeTags.Function,
        EdgeTags.Linker,
        EdgeTags.LinkRelation,
        EdgeTags.LinkArgument,
        EdgeTags.Ground,
        EdgeTags.Terminal,
        EdgeTags.Punctuation,
    ))}

    @staticmethod
    def get_head_terminal(node):
        while node.text is None:  # Not a terminal
            edges = [edge for edge in node.outgoing
                     if not edge.remote and not edge.child.implicit]
            if not edges:
                return None
            node = min(edges, key=lambda edge: FeatureExtractor.EDGE_PRIORITY.get(
                edge.tag, 0)).child
        return node

    @staticmethod
    def has_gaps(node):
        # Possibly the same as FoundationalNode.discontiguous
        return any(length > 0 for length in FeatureExtractor.gap_lengths(node))

    @staticmethod
    def gap_length_sum(node):
        return sum(FeatureExtractor.gap_lengths(node))

    @staticmethod
    def gap_lengths(node):
        terminals = node.get_terminals()
        return (t1.index - t2.index - 1 for (t1, t2) in zip(terminals[1:], terminals[:-1]))

    @staticmethod
    def gap_type(node):
        if node.text is not None:
            return "n"  # None
        if FeatureExtractor.has_gaps(node):
            return "p"  # Pass
        if any(child.text is None and FeatureExtractor.has_gaps(child)
               for child in node.children):
            return "s"  # Source
        return "n"  # None
