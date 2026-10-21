import unittest, os, tempfile
class T(unittest.TestCase):
    def test(self):
        os.environ['TODO_DB']=tempfile.mktemp()
        import todo
        todo.DB=os.environ['TODO_DB']
        self.assertEqual(todo.main(['done','5']),1)
