"""GTSinger source information; corpus acquisition is not enabled.

The provider has additional terms beyond CC BY-NC-SA. No acceptance is
recorded, no corpus data is downloaded and no training permission is inferred.
"""

SOURCE = 'https://huggingface.co/datasets/AaronZ345/GTSinger'
TERMS = 'https://github.com/AaronZ345/GTSinger/blob/main/dataset_license.md'


def status():
    return dict(source=SOURCE, terms=TERMS, acquisition_enabled=False,
                terms_accepted=False, training_started=False)


if __name__ == '__main__':
    import json
    print(json.dumps(status(), indent=2))
