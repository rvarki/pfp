#!/usr/bin/env python3

import utils.py

# Set this dir
data_base_dir = '/blue/boucher/marco.oliva/projects/experiments/pfp'
pre_download_data_dir = '/blue/boucher/marco.oliva/data/1kgp'

version_letter = 'a'

# Assuming installed
# - bcftools
# - htslib
# - gzip
# - bgzip

project_base_dir = os.path.dirname(os.path.abspath(__file__))
date_string             = datetime.datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
data_dir_bigbwt         = "{}/human_tests/{}/bigbwt".format(data_base_dir, date_string)
data_dir_pfp            = "{}/human_tests/{}/pfp".format(data_base_dir, date_string)
common_data_dir         = "{}/human_tests/{}/data".format(data_base_dir, date_string)
common_tools_dir        = "{}/human_tests/tools".format(data_base_dir)
tmp_fasta_dir           = "{}/human_tests/{}/data/tmp".format(data_base_dir, date_string)


# Chromosomes
chromosomes_list = [i for i in range(1, 23)]

w_value   = 10
p_value  = 100
n_threads  = 32

def get_vcf_files(out_dir):
    vcf_files_list = list()
    for chromosome_id in [str(c) for c in range(1,23)]:
        chromosome_file_name = "ALL.chr{}.phase3_shapeit2_mvncall_integrated_v5{}.20130502." \
                               "genotypes.vcf.gz".format(chromosome_id, version_letter)

        if (os.path.exists(pre_download_data_dir + '/vcf/' + chromosome_file_name)):
            rootLogger.info('Copying {}'.format(chromosome_file_name))
            execute_command('cp {} {}'.format(pre_download_data_dir + '/vcf/' + chromosome_file_name,
                                              out_dir + '/' + chromosome_file_name)
                            )
        else:
            rootLogger.info('VCF files have to be in {}'.format(pre_download_data_dir + '/vcf/'))
            exit()

        # Filter and index, if not existing
        rootLogger.info('Filtering out symbolyc allels from VCFs')
        execute_command('bcftools view -v snps,indels -m2 -M2 -Oz -o {outv} {inv}'.format(
            inv=out_dir + '/' + chromosome_file_name,
            outv=out_dir + '/' + chromosome_file_name[:-3] + '.filtered.bgz'), time_it=True)
        execute_command('bcftools index {}'.format(out_dir + '/' + chromosome_file_name[:-3] + '.filtered.bgz'), time_it=True)

        vcf_files_list.append(out_dir + '/' + chromosome_file_name[:-3] + '.filtered.bgz')
    return vcf_files_list

def get_reference_files(out_dir):
    out_fasta_list = list()
    for chromosome_id in [str(c) for c in chromosomes_list]:
        if (os.path.exists(pre_download_data_dir + '/reference/' + chromosome_id + '.fa.gz')):
            rootLogger.info('{} already exists'.format(pre_download_data_dir + '/reference/' + chromosome_id + '.fa.gz'))
            execute_command('cp {} {}'.format(pre_download_data_dir + '/reference/' + chromosome_id + '.fa.gz', out_dir + '/' + chromosome_id + '.fa.gz'))
        else:
            rootLogger.info('Reference files have to be in {}'.format(pre_download_data_dir + '/reference/'))
            exit()
        out_fasta_list.append(out_dir + '/' + chromosome_id + '.fa.gz')
    return out_fasta_list

def per_sample_fasta(samples_dir, ref_dir, vcf_files_list, sample):
    rootLogger.info('Running on sample: {}'.format(sample))

    sample_dir = samples_dir + '/' + sample
    mkdir_p(sample_dir)
    out_fasta_all_path = sample_dir + '/' + sample + '_ALL.fa'
    if os.path.exists(out_fasta_all_path):
        rootLogger.info('{} already exists, overwriting it'.format(out_fasta_all_path))
    out_fasta_all = open(out_fasta_all_path, 'w')
    for idx,vcf_file in enumerate(vcf_files_list):
        chromosome = str(idx + 1)
        ref_fasta = ref_dir + '/' + chromosome + '.fa.gz'
        out_fasta_single_chromosome = sample_dir + '/' + sample + '_' + chromosome + '.fa'
        extract_fasta(out_fasta_single_chromosome, ref_fasta, vcf_file, sample)
        with open(out_fasta_single_chromosome, 'r') as chr_file:
            out_fasta_all.write(chr_file.read())
    out_fasta_all.close()

def main():
    global rootLogger
    logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)

    fileHandler = logging.FileHandler("{}/{}_logfile.log".format('.', date_string))
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    parser = argparse.ArgumentParser(description='Testing stuff.')
    parser.add_argument('-s', dest='samples_file', type=str, help='File containing list of samples', required=True)
    parser.add_argument('-t', dest='threads', type=int, help='Number of threads to be used', required=True)
    args = parser.parse_args()

    # Get executables
    mkdir_p(common_tools_dir)
    pfp_exe = get_pfp(common_tools_dir)
    pscan_exe = get_pscan(common_tools_dir)

    # Start extracting samples
    if not os.path.exists(args.samples_file):
        rootLogger.info('{} does not exist'.format(args.samples_file))
        return

    with open(args.samples_file) as f_handler:
        samples = f_handler.readlines()
    samples = [x.strip() for x in samples]

    vcf_dir = common_data_dir + '/vcf'
    mkdir_p(vcf_dir)
    vcf_files_list = get_vcf_files(vcf_dir)

    ref_dir = common_data_dir + '/ref'
    mkdir_p(ref_dir)
    ref_files_list = get_reference_files(ref_dir)
    ref_files_list = ref_files_list[0:22]

    samples_dir = common_data_dir + '/samples'
    mkdir_p(samples_dir)

    # ============================================================

    # ------------------------------------------------------------
    # Parallel section
    pool = Pool(processes=args.threads)
    fixed_args = [samples_dir, ref_dir, vcf_files_list]
    execs = []
    for sample in samples:
        execs.append(fixed_args + [sample])

    for _ in tqdm.tqdm(pool.starmap(per_sample_fasta, execs), total=len(execs)):
        pass
    # ------------------------------------------------------------

    out_fasta_multi_sample = samples_dir + '/' + str(len(samples)) + '_samples.fa'
    if os.path.exists(out_fasta_multi_sample):
        rootLogger.info('{} already exists, overwriting it'.format(out_fasta_multi_sample))

    multi_sample_file = open(out_fasta_multi_sample, 'w')
    for sample in samples:
        sample_file_path = samples_dir + '/' + sample + '/' + sample + '_ALL.fa'
        with open(sample_file_path) as sample_file:
            multi_sample_file.write(sample_file.read())
    multi_sample_file.close()

    # ------------------------------------------------------------

    # Run pscan.x
    base_command = "{pscan} -t {c_threads} -f {file} -w {window} -p {modulo}"
    command = base_command.format(pscan=pscan_exe, c_threads=n_threads, file=out_fasta_multi_sample, window=w_value,
                                  modulo=p_value)
    execute_command(command, time_it=True)

    # ============================================================

    # Run pfp++
    mkdir_p(data_dir_pfp)
    pfp_config_file = create_pfp_config_file(vcf_files_list, ref_files_list, data_dir_pfp)
    base_command = "{pfp} --configure {config_file} -t {c_threads} -m {n_samples} " \
                   "--use-acceleration --print-statistics --occurrences -w {window} -p {modulo} -o {out_dir}"
    command = base_command.format(pfp=pfp_exe, c_threads=n_threads, window=w_value,
                                  modulo=p_value, config_file=pfp_config_file, n_samples=len(samples),
                                  out_dir=data_dir_pfp)
    execute_command(command, time_it=True)

if __name__ == '__main__':
    main()
