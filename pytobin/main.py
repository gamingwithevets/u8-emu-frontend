import sys
import importlib.util
import modelinfo

if __name__ == '__main__':
	if len(sys.argv) != 3:
		print(f'usage: {sys.argv[0]} [py config input] [bin config output]')
		sys.exit()

	spec = importlib.util.spec_from_file_location('config', sys.argv[1])
	if spec is None:
		print('invalid or non-existant config file')
		sys.exit()
	else:
		config = importlib.util.module_from_spec(spec)
		sys.modules['config'] = config
		spec.loader.exec_module(config)

	if hasattr(config, 'rom8') and config.rom8:
		print('ROM8 mode not supported on u8-emu-frontend-cpp')
		sys.exit()

	try:
		a = modelinfo.config(config)
		with open(sys.argv[2], 'wb') as f: a.to_file(f)
	except Exception as e:
		print(f'ERROR: {str(e)}')
