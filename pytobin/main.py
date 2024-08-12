import sys
import importlib
import modelinfo

if __name__ == '__main__':
	if len(sys.argv) != 3:
		print(f'usage: {sys.argv[0]} [py config input] [bin config output]')
		sys.exit()

	spec = importlib.util.spec_from_file_location('config', sys.argv[1])
	if spec is None:
		print(f'invalid or non-existant config file')
		sys.exit()
	else:
		config = importlib.util.module_from_spec(spec)
		sys.modules['config'] = config
		spec.loader.exec_module(config)

	a = modelinfo.config(config)
	with open(sys.argv[2], 'wb') as f: a.to_file(f)
