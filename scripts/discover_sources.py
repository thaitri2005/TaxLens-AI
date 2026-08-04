import argparse
import json

from taxlens.ingestion.connectors import create_official_connector


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover official legal documents without downloading them"
    )
    parser.add_argument("--source", choices=("mof", "government"), required=True)
    args = parser.parse_args()
    connector = create_official_connector(args.source)
    documents = connector.list_documents()
    print(
        json.dumps(
            [
                {
                    "source_name": document.source_name,
                    "document_number": document.document_number,
                    "title": document.title,
                    "content_url": document.content_url,
                }
                for document in documents
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
