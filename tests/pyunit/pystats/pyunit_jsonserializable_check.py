# Copyright (c) 2022 The Regents of The University of California
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Recursive JSON serialization through the gem5 26 statistics visitor.

SerializableStat was removed upstream after serialization moved into visitors.
Use supported typed statistics, preserving nested objects, ordered lists,
numeric/string JSON primitives and null optional metadata from the old test.
"""
import json
import unittest

from m5.ext.pystats.group import (
    Group,
    SimObjectGroup,
    SimObjectVectorGroup,
)
from m5.ext.pystats.statistic import Scalar, Vector
from m5.ext.pystats.storagetype import StorageType
from m5.stats.gem5stats import JsonOutputVistor


def nested_stats():
    numeric_values = [1, 2, 3, 4, 5.2, 0]
    descriptions = ["1", None, "3", None, None, None]
    vector = Vector(
        value={
            index: Scalar(
                value=value,
                description=description,
                datatype=StorageType.f64
                if isinstance(value, float)
                else StorageType.u32,
            )
            for index, (value, description) in enumerate(
                zip(numeric_values, descriptions)
            )
        },
        type="Vector",
    )
    return Group(
        type="Group",
        child_1=Group(
            type="Group",
            stat1=Scalar(2, datatype=StorageType.u32),
            stat2=Scalar(3, unit="3", datatype=StorageType.u32),
        ),
        child_list=SimObjectVectorGroup(
            children=[
                SimObjectGroup(
                    name="first",
                    stat1=Scalar(1, description="hello", datatype=StorageType.u32),
                ),
                SimObjectGroup(name="second", list_stat2=vector),
            ]
        ),
    )


class JsonSerializableTestSuite(unittest.TestCase):
    def test_to_json(self):
        # Visiting synthetic typed stats does not touch the output file.
        visitor = JsonOutputVistor("unused-json-output.json")
        obj_json = nested_stats().accept(visitor)
        self.assertEqual(obj_json["child_1"]["stat1"]["value"], 2)
        self.assertEqual(obj_json["child_1"]["stat2"]["unit"], "3")
        children = obj_json["child_list"]["value"]
        self.assertEqual(len(children), 2)
        self.assertEqual([child["name"] for child in children], ["first", "second"])
        self.assertEqual(children[0]["stat1"]["description"], "hello")
        vector = children[1]["list_stat2"]["value"]
        self.assertEqual(list(vector), [0, 1, 2, 3, 4, 5])
        self.assertEqual(
            [stat["value"] for stat in vector.values()], [1, 2, 3, 4, 5.2, 0]
        )
        self.assertEqual(vector[0]["description"], "1")
        self.assertEqual(vector[2]["description"], "3")
        self.assertEqual(vector[4]["datatype"], "f64")
        self.assertIsNone(vector[5]["unit"])
        self.assertIsNone(vector[5]["description"])
        # Exercise actual JSON encoding as well as the visitor's dictionary.
        decoded = json.loads(json.dumps(obj_json))
        encoded_vector = decoded["child_list"]["value"][1]["list_stat2"]["value"]
        self.assertEqual(list(encoded_vector), ["0", "1", "2", "3", "4", "5"])
        self.assertEqual(encoded_vector["4"]["value"], 5.2)
        self.assertIsNone(encoded_vector["5"]["description"])

    def test_non_statistic_group_children_are_rejected(self):
        # Raw attributes belonged to the retired SerializableStat contract.
        # The public visitor now requires typed statistic/group children.
        visitor = JsonOutputVistor("unused-json-output.json")
        for value in (None, "raw string", 2, [1, 2]):
            with self.subTest(value=value):
                with self.assertRaisesRegex(AssertionError, "Unexpected value type"):
                    Group(type="Group", invalid=value).accept(visitor)
