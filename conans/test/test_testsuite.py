import os


class TestTestSuite(object):

    def test_duplicate_names(self):
        files_list = []
        duplicates = []
        exclude_folders = ["assets"]
        root = os.path.dirname(__file__)
        for item in os.walk(root):
            if os.path.basename(os.path.normpath(item[0])) not in exclude_folders:
                filenames = item[2]
                for filename in filenames:
                    if filename[-3:] == ".py":
                        if filename.split(".")[0][:4] != "test" and filename.split(".")[0][-4:] != "test":
                            with open(os.path.join(item[0], filename)) as possible_test_file:
                                contents = possible_test_file.read()
                                if "def test" in contents and "assert" in contents:
                                    raise Exception("Wrong name for {} test file. All test file"
                                                    " names must be pre or post fixed with test"
                                                    .format(os.path.join(item[0], filename)))
                        else:
                            if filename not in files_list:
                                files_list.append(filename)
                            else:
                                duplicates.append(filename)
        assert len(duplicates) == 0, "File names for test files should be unique. " \
                                     "These file names are duplicated: {}".format(str(duplicates))
