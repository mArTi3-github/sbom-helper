# Про SBOM
Текущая задача, которую нужно выполнить, связана с обработкой SBOM.
Обобщенное описание формата CycloneDX SBOM можно изучить по ссылке https://cyclonedx.org/docs/1.6/json/ . Расширенное описание стандарта CycloneDX SBOM, описывающее, как оформляются ссылки на исходные тексты компонентов, приведено в файле @.misc/addictional_materials/sbom_description_fstec.md . Примеры файлов, соответствующих указанному расширенному описанию формата, также приведены в папке @.misc/addictional_materials/ . Пример корректного SBOM-файла со всеми необходимыми ссылками на исходные тексты: @.misc/addictional_materials/sbom_example_correct.json , пример SBOM-файла, в котором не хватает части ссылок: @.misc/addictional_materials/sbom_example_missed_references.json . Эти файлы можно использовать при проведении тестирования.

# Про PURL
Описание спецификации PURL представлено в README.md репозитория https://github.com/package-url/purl-spec
