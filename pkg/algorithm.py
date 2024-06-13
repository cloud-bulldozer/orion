"""Module for Generic Algorithm class"""
class Algorithm:
    """Generic Algorithm class for algorithm factory
    """
    def __init__(self, matcher, dataframe, test):
        self.matcher = matcher
        self.dataframe = dataframe
        self.test = test

    def output_json(self):
        """Outputs the data in json format
        """

    def output_text(self):
        """Outputs the data in text/tabular format
        """

    def output(self,output_format):
        """Method to select output method

        Args:
            output_format (str): format of the output

        Raises:
            ValueError: In case of unmatched output

        Returns:
            method: return method to be used
        """
        if output_format=="json":
            return self.output_json()
        if output_format=="text":
            return self.output_text()
        raise ValueError("Unsupported output format {output_format} selected")
