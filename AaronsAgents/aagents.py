import sys


def aa_main():
    try:
        print("Hello World")
    except SystemExit:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as ex:
        print(f"Unhandled exception: {ex}")
        sys.exit(1)
    sys.exit(0)