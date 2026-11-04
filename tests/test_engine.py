import unittest, tempfile, subprocess, json
from PIL import Image
from png_to_claude_code.engine import cells, build, art


class BannerTests(unittest.TestCase):
    def test_alpha_and_two_pixel_cell_colors(self):
        im = Image.new("RGBA", (3, 2), (0, 0, 0, 0))
        im.putpixel((0, 0), (10, 20, 30, 255))
        im.putpixel((1, 1), (40, 50, 60, 255))
        im.putpixel((2, 0), (255, 0, 0, 255))
        im.putpixel((2, 1), (0, 0, 255, 255))
        self.assertEqual(
            cells(im),
            [
                [
                    ("#0a141e", None, "▀"),
                    ("#28323c", None, "▄"),
                    ("#ff0000", "#0000ff", "▀"),
                ]
            ],
        )

    def test_source_loaded_as_latin1_still_renders_block_characters(self):
        with tempfile.TemporaryDirectory() as td:
            path = __import__("pathlib").Path(td) / "test.png"
            im = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
            im.putpixel((0, 0), (255, 255, 255, 255))
            im.save(path)
            stub, _ = art(path, 2)
            js = (
                'const rt=()=>false,n="text",s="box",e=(type,props)=>({type,...props});'
                + stub.decode("latin1")
                + ";console.log(JSON.stringify(ul({})));"
            )
            result = json.loads(subprocess.check_output(["node", "-e", js]))
            self.assertEqual(result["children"][0]["children"][0]["children"], "▀")

    def test_unknown_binary_is_rejected(self):
        with self.assertRaises(ValueError):
            build(b"not a Claude executable", b"function ul(m){}")


if __name__ == "__main__":
    unittest.main()
